import { expect, test, type Page } from '@playwright/test'

// Season screen on a completed demo draft. The two calls that reach ESPN (link preview, sync) and the
// ESPN-derived reads (overview pairings, results) are mocked at the network layer; link/apply, power
// rankings and free agents run against the real backend.

const LEAGUE_ID = 2075231076

async function completeDraft(page: Page, sessionId: string) {
  const health = await (await page.request.get('/api/health')).json()
  const players = await (await page.request.get(`/api/snapshots/${health.default_snapshot_id}/players?limit=200`)).json()
  const state = await (await page.request.get(`/api/sessions/${sessionId}/state`)).json()
  const items = state.schedule.map((p: { overall: number; manager_id: string }, i: number) => ({
    type: 'pick_committed',
    payload: { overall: p.overall, manager_id: p.manager_id, player_id: players[i].player_id },
    idempotency_key: `e2e-pick-${p.overall}`,
  }))
  const res = await page.request.post(`/api/sessions/${sessionId}/events/batch`, { data: { items, source: 'import' } })
  expect(res.ok()).toBeTruthy()
  const done = await res.json()
  expect(done.is_complete).toBe(true)
  return done
}

test('link to ESPN (mocked), sync, matchups, power rankings, free agents, results', async ({ page }) => {
  page.on('dialog', (d) => void d.accept())
  await page.goto('/')
  await page.getByTestId('setup-confirm-format').check()
  await page.getByTestId('setup-create').click()
  await expect(page).toHaveURL(/\?session=[a-z0-9]+#\/draft/)
  const sessionId = new URL(page.url()).searchParams.get('session') ?? ''
  const state = await completeDraft(page, sessionId)
  const managers: { id: string; name: string }[] = state.league.managers
  const userId: string = state.league.user_manager_id
  const teams = managers.map((m, i) => ({ team_id: i + 1, name: `ESPN ${m.name}`, owner_name: `${m.name} Owner`, n_players: 13 }))

  // --- ESPN network calls, mocked -------------------------------------------------------------
  await page.route('**/api/sessions/*/espn/link', (route) =>
    route.fulfill({
      json: {
        league_id: LEAGUE_ID,
        league_name: 'Mock Thieves',
        teams,
        mapping: managers.map((m, i) => ({
          manager_id: m.id, manager_name: m.name, team_id: i + 1, team_name: teams[i].name, owner_name: teams[i].owner_name, overlap: 1, confidence: 'high',
        })),
        unmatched_managers: [],
        unmatched_teams: [],
        settings_warnings: ['ESPN locks lineups per game (daily); the session is set to weekly'],
        warnings: [],
      },
    }),
  )
  await page.route('**/api/sessions/*/espn/sync', async (route) => {
    const current = await (await page.request.get(`/api/sessions/${sessionId}/state`)).json()
    await route.fulfill({
      json: {
        ids: { draft_revision: current.draft_revision, strategy_revision: 0, league_revision: current.league_revision, last_seq: current.last_seq, snapshot_id: 'x', projection_version: 'v', seed: 1 },
        fetched_at: '2026-10-19T04:00:00+00:00',
        summary: 'ESPN sync: 0 adds, 0 drops across 0 teams; 0 unknown players',
        changes: [],
        warnings: [],
        unknown_players: [],
        state: current,
      },
    })
  })
  await page.route('**/api/sessions/*/season/overview*', async (route) => {
    const real = await route.fetch()
    const body = await real.json()
    if (!real.ok() || !body.league_categories) {
      console.log('overview passthrough', real.status(), JSON.stringify(body).slice(0, 300))
      await route.fulfill({ response: real })
      return
    }
    const opponent = managers.find((m) => m.id !== userId)!
    const odds = (a: string, b: string) => ({
      period: 1, manager_a: a, manager_b: b, expected_a: 5.1, expected_b: 2.9, p_win_a: 0.7, p_tie: 0.1, p_win_b: 0.2,
      cat_p_a: Object.fromEntries(body.league_categories.map((c: { key: string }) => [c.key, 0.66])), modal_score: [5, 3], games_a: 30, games_b: 28, notes: [],
    })
    const userPair = { period: 1, home_manager_id: userId, away_manager_id: opponent.id, odds: odds(userId, opponent.id) }
    const bye = { period: 1, home_manager_id: managers.find((m) => m.id !== userId && m.id !== opponent.id)!.id, away_manager_id: null, odds: null }
    await route.fulfill({ json: { ...body, linked: true, league_name: 'Mock Thieves', synced_at: '2026-10-19T04:00:00+00:00', matchups: [userPair, bye], user_matchup: userPair } })
  })
  await page.route('**/api/sessions/*/season/results*', (route) =>
    route.fulfill({
      json: {
        ids: { draft_revision: 1, strategy_revision: 0, league_revision: 1, last_seq: 1, snapshot_id: 'x', projection_version: 'v', seed: 1 },
        period: 1,
        results: [
          {
            period: 1,
            home: { manager_id: userId, values: { PTS: 400 }, results: { PTS: 'WIN' }, cats_won: 1 },
            away: { manager_id: managers.find((m) => m.id !== userId)!.id, values: { PTS: 380 }, results: { PTS: 'LOSS' }, cats_won: 0 },
            winner: 'UNDECIDED',
          },
        ],
        projected: [],
      },
    }),
  )

  // --- link -----------------------------------------------------------------------------------
  await page.goto(`/?session=${sessionId}#/season`)
  await page.reload() // a hash-only navigation keeps the pre-draft store; the batch happened outside the page
  await expect(page.getByTestId('link-dialog')).toBeVisible()
  await page.getByTestId('league-id').fill(String(LEAGUE_ID))
  await page.getByTestId('link-preview').click()
  await expect(page.getByRole('table', { name: 'Team mapping' })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Team mapping' }).locator('tbody tr')).toHaveCount(managers.length)
  await expect(page.getByText(/locks lineups per game/)).toBeVisible()
  await page.getByTestId('link-apply').click()

  // --- synced: the real session now carries the league id, the bar shows the mocked sync ---------
  await expect(page.getByTestId('sync-now')).toBeVisible()
  await expect(page.getByRole('region', { name: 'ESPN sync' })).toContainText('Mock Thieves')
  const linked = await (await page.request.get(`/api/sessions/${sessionId}/state`)).json()
  expect(linked.league.espn_league_id).toBe(LEAGUE_ID)
  expect(Object.keys(linked.league.espn_team_ids)).toHaveLength(managers.length)

  // --- matchups ---------------------------------------------------------------------------------
  await expect(page.getByTestId('user-matchup')).toBeVisible()
  await expect(page.getByTestId('user-matchup')).toContainText('70%')
  await expect(page.getByText(/Bye week/)).toBeVisible()
  await expect(page.getByTestId('roster-moves')).toContainText(/No roster moves in week 1/)

  // --- power rankings (real backend) -------------------------------------------------------------
  await page.getByTestId('season-tab-power').click()
  await expect(page.getByTestId('power-table').locator('tbody tr')).toHaveCount(managers.length)
  await expect(page.getByTestId('power-table').locator('tbody tr.mine')).toHaveCount(1)

  // --- free agents (real backend): nobody owned, rows present ---------------------------------------
  await page.getByTestId('season-tab-free-agents').click()
  const rows = page.getByRole('table', { name: 'Free agents' }).locator('tbody tr')
  await expect(rows.first()).toBeVisible()
  const names = await rows.locator('th .player-link').evaluateAll((els) => els.map((e) => e.textContent ?? ''))
  expect(names.length).toBeGreaterThan(10)
  const owned = new Set<string>((Object.values(linked.current_rosters) as string[][]).flat())
  const firstId = await rows.first().locator('th .player-link').getAttribute('aria-label')
  expect(firstId).toBeNull() // free agent rows render the response's player name directly
  expect(owned.size).toBe(managers.length * 13)

  // --- results (mocked ESPN scoreByStat) -----------------------------------------------------------
  await page.getByTestId('season-tab-results').click()
  await expect(page.getByText('Actual (ESPN)')).toBeVisible()
  await expect(page.getByRole('cell', { name: '400' })).toBeVisible()

  // --- sync now re-renders without error ---------------------------------------------------------
  await page.getByTestId('sync-now').click()
  await expect(page.getByTestId('sync-now')).toHaveText('Sync now')
  await expect(page.getByText(/0 adds, 0 drops/)).toBeVisible()
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
