import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PerformersResponse } from '../api/types'
import { Diverging } from '../components/charts/Diverging'
import { Scatter } from '../components/charts/Scatter'
import { Explainer } from '../components/performers/Explainer'
import { LeaderboardCard } from '../components/performers/LeaderboardCard'
import { PerformerTable, type Metric } from '../components/performers/PerformerTable'
import { ChartFrame } from '../components/ui/ChartFrame'
import { Icon } from '../components/ui/Icon'
import { PageHeader, type ContextChip } from '../components/ui/PageHeader'
import { Segmented } from '../components/ui/Segmented'
import { StatCard, StatRow } from '../components/ui/StatCard'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { fmtNum, fmtSigned } from '../lib/format'
import { readHashQuery, replaceHashQuery } from '../lib/hashQuery'
import { buildUrl } from '../lib/router'
import { teamColor } from '../lib/teamColors'
import { useDraftStore } from '../store/draftStore'

type Scope = 'week' | 'season'

const CONTRIB_TIP = 'Top contributors: Σ over categories of (per-game stat ÷ unit size) × games ESPN counted for this team. One unit = one standard deviation of per-game production across the league pool; FG%/FT% as shooting impact; turnovers count against.'
const OVER_TIP = 'Biggest overperformers: contribution minus expected, where expected = the same formula on the projected per-game line × the games actually played. No projection or no games = not ranked.'

/** Team performers: who produced the most for a fantasy team, and who beat their projection by the most. */
export function PerformersScreen() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const isDemo = useDraftStore((s) => s.snapshot?.is_demo ?? false)
  const initial = readHashQuery(window.location.hash)
  const [manager, setManager] = useState<string | null>(initial.team ?? null)
  const [scope, setScope] = useState<Scope>(initial.scope === 'season' ? 'season' : 'week')
  const [period, setPeriod] = useState<number | null>(/^\d+$/.test(initial.week ?? '') ? Number(initial.week) : null)
  const [metric, setMetric] = useState<Metric>('contribution')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [data, setData] = useState<PerformersResponse | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  const managerId = manager ?? state?.league.user_manager_id ?? null

  useEffect(() => {
    if (!sessionId || !managerId) return
    let cancelled = false
    setStatus('loading')
    setError(null)
    setData(null)
    api
      .seasonPerformers(sessionId, managerId, scope === 'week' ? period : null)
      .then((res) => {
        if (cancelled) return
        setData(res)
        setStatus('ready')
        if (scope === 'week' && period === null && res.periods_available.length) setPeriod(res.periods_available[res.periods_available.length - 1])
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setStatus('error')
        setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, managerId, scope, period])

  useEffect(() => {
    replaceHashQuery({ team: manager, scope: scope === 'season' ? 'season' : null, week: scope === 'week' && period !== null ? String(period) : null })
  }, [manager, scope, period])

  if (!sessionId || !state) {
    return (
      <EmptyState title="No session loaded" action={<a href={buildUrl('setup', null)}>Go to setup</a>}>
        Performers are computed from ESPN box scores for a drafted, linked session.
      </EmptyState>
    )
  }
  if (!state.is_complete) {
    return <EmptyState title="Team performers open once the draft is complete and the league is synced from ESPN" />
  }
  const periods = data?.periods_available ?? []
  const rows = data ? (metric === 'contribution' ? data.contributors : data.overperformers) : []
  const teamName = state.league.managers.find((m) => m.id === managerId)?.name ?? managerId ?? ''
  const withBaseline = data ? data.contributors.filter((r) => r.over_expected !== null) : []
  const totalContribution = data ? data.contributors.reduce((a, r) => a + r.contribution, 0) : 0
  const totalExpected = withBaseline.reduce((a, r) => a + (r.expected_contribution ?? 0), 0)
  const totalOver = withBaseline.reduce((a, r) => a + (r.over_expected ?? 0), 0)
  const totalGames = data ? data.contributors.reduce((a, r) => a + r.games, 0) : 0
  const select = (id: string) => {
    setSelectedId(id)
    setOpenId(id)
  }
  const chips: ContextChip[] = [{ label: 'Team', value: teamName, tone: managerId === state.league.user_manager_id ? 'amber' : 'neutral' }]
  if (data) chips.push({ label: scope === 'week' ? 'Week' : 'Scope', value: scope === 'week' ? data.period ?? '—' : `season · ${periods.length} wk` })
  if (isDemo) chips.push({ label: 'Data', value: 'demo', tone: 'demo' })

  return (
    <div className="stack performers-screen" data-testid="performers">
      <PageHeader
        title="Team performers"
        description="Who produced the most for a fantasy team, and who beat their projection by the most. Built from ESPN's applied box scores per matchup week; expected = projection per game × games actually played."
        chips={chips}
        filters={
          <>
            <span className="field">
              <label htmlFor="perf-team">Team</label>
              <select
                id="perf-team"
                value={managerId ?? ''}
                onChange={(e) => {
                  setManager(e.target.value)
                  setSelectedId(null)
                  setOpenId(null)
                }}
                data-testid="perf-team"
              >
                {state.league.managers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                    {m.id === state.league.user_manager_id ? ' (you)' : ''}
                  </option>
                ))}
              </select>
            </span>
            <Segmented<Scope>
              variant="pill"
              label="Scope"
              value={scope}
              onChange={setScope}
              options={[
                { id: 'week', label: 'Weekly', testId: 'scope-week' },
                { id: 'season', label: 'Season to date', testId: 'scope-season' },
              ]}
            />
            {scope === 'week' && (
              <span className="field">
                <label htmlFor="perf-week">Week</label>
                <select id="perf-week" value={period ?? ''} onChange={(e) => setPeriod(Number(e.target.value))} disabled={periods.length === 0} data-testid="perf-week">
                  {periods.length === 0 && <option value="">No weeks synced yet</option>}
                  {periods.map((p) => (
                    <option key={p} value={p}>
                      Week {p}
                    </option>
                  ))}
                </select>
              </span>
            )}
            {(selectedId || openId) && (
              <button
                type="button"
                className="small ghost"
                onClick={() => {
                  setSelectedId(null)
                  setOpenId(null)
                }}
              >
                <Icon name="close" size={12} /> Clear selection
              </button>
            )}
            {data && (
              <span className="status" title={data.baseline}>
                Source: {data.source}
              </span>
            )}
          </>
        }
      />

      {status === 'loading' && !data && <LoadingState title="Loading box scores" />}
      {status === 'error' && <ErrorState title="Could not load performers">{error}</ErrorState>}
      {data && data.contributors.length === 0 && (
        <EmptyState title="No box scores for this selection yet">{data.notes.join(' ') || 'Sync the league after games have been played; weekly stats fill in as ESPN applies them.'}</EmptyState>
      )}
      {data && data.contributors.length > 0 && (
        <>
          <StatRow>
            <StatCard label="Team contribution" value={fmtNum(totalContribution, 1)} detail={`units · ${data.contributors.length} players`} />
            <StatCard label="Expected" value={withBaseline.length ? fmtNum(totalExpected, 1) : '—'} detail={withBaseline.length ? `${withBaseline.length} players with a baseline` : 'no baselines'} />
            <StatCard
              label="Vs expected"
              value={withBaseline.length ? fmtSigned(totalOver, 1) : '—'}
              detail="players with a baseline only"
              tone={withBaseline.length ? (totalOver >= 0 ? 'good' : 'bad') : 'neutral'}
            />
            <StatCard label="Games counted" value={totalGames} detail={scope === 'week' ? 'this week' : `across ${periods.length} week${periods.length === 1 ? '' : 's'}`} />
          </StatRow>
          <div className="leaderboards">
            <LeaderboardCard title="Top contributors" tooltip={CONTRIB_TIP} rows={data.contributors} metric="contribution" testId="top-contributors" selectedId={selectedId} onSelect={select} />
            <LeaderboardCard title="Biggest overperformers" tooltip={OVER_TIP} rows={data.overperformers} metric="over_expected" testId="top-overperformers" selectedId={selectedId} onSelect={select} />
          </div>
          <div className="perf-charts">
            <ChartFrame
              title="Performance vs expectation"
              description="Contribution minus expected, per player. Right of zero beat the projection; left fell short. Players without a baseline are not shown."
              help="Expected = projected per-game line × games actually played, so missed games do not count against anyone."
              legend={[
                { label: 'above expectation', swatch: 'good' },
                { label: 'below expectation', swatch: 'bad' },
              ]}
              unavailable={withBaseline.length === 0 ? 'No player on this team has a projection baseline for this selection.' : undefined}
              testId="chart-diverging"
            >
              <Diverging
                rows={[...withBaseline]
                  .sort((a, b) => (b.over_expected ?? 0) - (a.over_expected ?? 0))
                  .map((r) => ({ id: r.player.player_id, label: r.player.name, value: r.over_expected ?? 0, sublabel: `${r.games} GP` }))}
                format={(v) => v.toFixed(1)}
                unit="units"
                selectedId={selectedId}
                onSelect={select}
              />
            </ChartFrame>
            <ChartFrame
              title="Actual vs expected contribution"
              description="One point per player. The dashed diagonal is 'exactly as projected'; distance above it is overperformance."
              legend={[{ label: 'player (team colour)', swatch: 'team' }]}
              unavailable={withBaseline.length === 0 ? 'Needs players with both a contribution and an expected value.' : undefined}
              testId="chart-scatter"
            >
              <Scatter
                points={data.contributors.map((r) => ({ id: r.player.player_id, label: r.player.name, x: r.expected_contribution, y: r.contribution, color: teamColor(r.player.team).primary }))}
                xLabel="Expected"
                yLabel="Actual"
                format={(v) => v.toFixed(0)}
                selectedId={selectedId}
                onSelect={select}
              />
            </ChartFrame>
            <ChartFrame
              title="Week-by-week trend"
              unavailable="Needs per-week observations per player. The performers endpoint returns one scope at a time (a single week, or season totals), so there is no history to draw yet; use the week selector to step through weeks."
              testId="chart-trend"
            >
              <span />
            </ChartFrame>
          </div>
          <section className="panel">
            <div className="panel-head">
              <h2>All players</h2>
              <Segmented<Metric>
                variant="pill"
                label="Ranking"
                value={metric}
                onChange={setMetric}
                options={[
                  { id: 'contribution', label: 'By contribution' },
                  { id: 'over_expected', label: 'By performance vs expected' },
                ]}
              />
            </div>
            <PerformerTable rows={rows} metric={metric} selectedId={selectedId} onSelect={setSelectedId} openId={openId} onOpenChange={setOpenId} />
            {data.notes.length > 0 && (
              <ul className="table-note" style={{ paddingLeft: 18 }}>
                {data.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
      {data && <Explainer unitSizes={data.unit_sizes} benchmarkRates={data.benchmark_rates} categories={data.categories} />}
    </div>
  )
}
