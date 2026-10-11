import { expect, test } from '@playwright/test'

// Strategy changes re-rank immediately with new revision ids; a picks CSV import lands as a batch;
// the session export round-trips through the import file input.

test('punt change updates the category profile and rankings; CSV picks import; export/import', async ({ page }) => {
  page.on('dialog', (d) => void d.accept())
  await page.goto('/')
  await page.getByTestId('setup-confirm-format').check()
  await page.getByTestId('setup-create').click()
  await expect(page).toHaveURL(/\?session=[a-z0-9]+#\/draft/)
  const sessionId = new URL(page.url()).searchParams.get('session') ?? ''
  await expect(page.getByTestId('rec-name')).toBeVisible()
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)

  // --- fixed punt on FT% ------------------------------------------------------------------
  const before = await page.locator('[data-testid="shortlist-row"]').evaluateAll((rows) => rows.map((r) => r.getAttribute('data-player-id')))
  await page.getByTestId('tab-strategy').click()
  await page.getByRole('radio', { name: /FT%.*fixed punt/i }).check()
  await expect(page.getByTestId('top-save-status')).toHaveText('saved')
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)
  await page.getByTestId('tab-categories').click()
  await expect(page.locator('[data-testid="category-profile"] [data-cat="FT_PCT"]')).toContainText('fixed')
  const after = await page.locator('[data-testid="shortlist-row"]').evaluateAll((rows) => rows.map((r) => r.getAttribute('data-player-id')))
  expect(after).not.toEqual(before)

  // --- picks import through the setup screen ----------------------------------------------
  const names = await page.locator('[data-testid="picker-row"][data-drafted="false"] [data-testid="picker-name"]').evaluateAll((els) => els.slice(0, 2).map((e) => e.textContent ?? ''))
  expect(names.length).toBe(2)
  await page.goto(`/?session=${sessionId}#/setup`)
  await expect(page.getByTestId('import-panel')).toBeVisible()
  await page.getByTestId('import-kind').selectOption('picks')
  await page.getByTestId('import-text').fill(`overall,manager_id,name\n1,m01,${names[0]}\n2,m02,${names[1]}\n`)
  await page.getByTestId('import-preview').click()
  await expect(page.getByTestId('import-preview-table')).toBeVisible()
  await page.getByTestId('import-apply').click()
  await page.goto(`/?session=${sessionId}#/draft`)
  await expect(page.getByTestId('top-on-clock')).toHaveText('Team 3')
  await page.getByTestId('tab-board').click()
  await expect(page.locator('[data-testid="board-cell-1"]')).toHaveAttribute('data-filled', 'true')

  // --- export then import as a new session -------------------------------------------------
  const exported = await page.evaluate(async (id) => (await fetch(`/api/sessions/${id}/export`)).json(), sessionId)
  expect(exported.events.length).toBeGreaterThanOrEqual(4)
  const imported = await page.evaluate(async (body) => (await fetch('/api/sessions/import', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).json(), exported)
  await page.goto(`/?session=${imported.id}#/draft`)
  await expect(page.getByTestId('top-on-clock')).toHaveText('Team 3')
  await page.getByTestId('tab-categories').click()
  await expect(page.locator('[data-testid="category-profile"] [data-cat="FT_PCT"]')).toContainText('fixed')
})

test('league profiles update per pick; any player can be previewed; breakdown rows expand', async ({ page }) => {
  page.on('dialog', (d) => void d.accept())
  await page.goto('/')
  await page.getByTestId('setup-confirm-format').check()
  await page.getByTestId('setup-create').click()
  await expect(page).toHaveURL(/\?session=[a-z0-9]+#\/draft/)
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)

  // preview a player from the picker who is not the highlighted recommendation
  const rows = page.locator('[data-testid="picker-row"][data-drafted="false"]')
  await expect(rows.first()).toBeVisible()
  const highlighted = await page.getByTestId('rec-name').getAttribute('data-player-id')
  const target = rows.nth(5)
  const targetId = await target.getAttribute('data-player-id')
  expect(targetId).not.toBe(highlighted)
  await target.getByRole('button', { name: /preview/i }).click()
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)
  await page.getByTestId('tab-categories').click()
  await expect(page.locator('[data-testid="category-profile"]')).toBeVisible()
  const profileHead = page.locator('#cats-h')
  await expect(profileHead).toContainText(/if I draft/)
  await expect(page.locator('[data-testid="category-profile"] [data-cat="PTS"]')).toContainText('+')
  await page.getByRole('button', { name: /stop preview|previewing|clear preview/i }).first().click()

  // expand the first shortlist row: full nine-category breakdown
  await page.locator('[data-testid="shortlist-expand"]').first().click()
  const breakdown = page.locator('[data-testid="shortlist-breakdown"]').first()
  await expect(breakdown).toBeVisible()
  await expect(breakdown).toContainText('Weighted by your strategy')
  await expect(breakdown.locator('thead th')).toHaveCount(10)

  // league profiles tab reflects a committed pick
  await page.getByTestId('tab-profiles').click()
  const profiles = page.locator('[data-testid="league-profiles"]')
  await expect(profiles).toHaveAttribute('aria-busy', 'false')
  await expect(profiles.locator('[data-testid="profile-row"]')).toHaveCount(12)
  await expect(profiles.locator('[data-manager-id="m01"] td').first()).toHaveText('0')
  await page.locator('body').press('/')
  await page.getByTestId('picker-search').press('Enter')
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('top-save-status')).toHaveText('saved')
  await expect(profiles).toHaveAttribute('aria-busy', 'false')
  await expect(profiles.locator('[data-manager-id="m01"] td').first()).toHaveText('1')
  await expect(profiles.locator('[data-manager-id="m01"]')).toContainText('#1')
})
