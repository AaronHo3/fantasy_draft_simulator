import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PerformersResponse } from '../api/types'
import { Explainer } from '../components/performers/Explainer'
import { LeaderboardCard } from '../components/performers/LeaderboardCard'
import { PerformerTable, type Metric } from '../components/performers/PerformerTable'
import { buildUrl } from '../lib/router'
import { useDraftStore } from '../store/draftStore'

type Scope = 'week' | 'season'

const CONTRIB_TIP = 'Top contributors: Σ over categories of (per-game stat ÷ unit size) × games ESPN counted for this team. One unit = one standard deviation of per-game production across the league pool; FG%/FT% as shooting impact; turnovers count against. See "How contribution and expected are calculated" below.'
const OVER_TIP = 'Biggest overperformers: contribution minus expected, where expected = the same formula on the player\'s projected per-game line × the games he actually played. Baseline: the snapshot\'s per-game projection (learned model blended with ESPN, with rookie and injury-return adjustments). No projection or no games = not ranked.'

/** Team performers: who produced the most for a fantasy team, and who beat their projection by the most. */
export function PerformersScreen() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const [manager, setManager] = useState<string | null>(null)
  const [scope, setScope] = useState<Scope>('week')
  const [period, setPeriod] = useState<number | null>(null)
  const [metric, setMetric] = useState<Metric>('contribution')
  const [data, setData] = useState<PerformersResponse | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  const managerId = manager ?? state?.league.user_manager_id ?? null

  useEffect(() => {
    if (!sessionId || !managerId) return
    let cancelled = false
    setStatus('loading')
    setError(null)
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

  if (!sessionId || !state) {
    return (
      <div className="panel">
        <p>No session loaded.</p>
        <a href={buildUrl('setup', null)}>Go to setup</a>
      </div>
    )
  }
  if (!state.is_complete) {
    return (
      <div className="panel">
        <p>Team performers are available once the draft is complete and the league is synced from ESPN.</p>
      </div>
    )
  }
  const periods = data?.periods_available ?? []
  const rows = data ? (metric === 'contribution' ? data.contributors : data.overperformers) : []
  return (
    <div className="stack performers-screen" data-testid="performers">
      <section className="panel">
        <div className="row between wrap">
          <div className="row">
            <label htmlFor="perf-team">Team</label>
            <select id="perf-team" value={managerId ?? ''} onChange={(e) => setManager(e.target.value)} data-testid="perf-team">
              {state.league.managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                  {m.id === state.league.user_manager_id ? ' (you)' : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="tabs" role="tablist" aria-label="Scope" style={{ borderBottom: 'none', marginBottom: 0 }}>
            <button type="button" role="tab" aria-selected={scope === 'week'} onClick={() => setScope('week')} data-testid="scope-week">
              Weekly
            </button>
            <button type="button" role="tab" aria-selected={scope === 'season'} onClick={() => setScope('season')} data-testid="scope-season">
              Season to date
            </button>
          </div>
          {scope === 'week' && (
            <div className="row">
              <label htmlFor="perf-week">Week</label>
              <select id="perf-week" value={period ?? ''} onChange={(e) => setPeriod(Number(e.target.value))} disabled={periods.length === 0} data-testid="perf-week">
                {periods.length === 0 && <option value="">No weeks synced yet</option>}
                {periods.map((p) => (
                  <option key={p} value={p}>
                    Week {p}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        {data && (
          <p className="muted" style={{ marginTop: 6, fontSize: 12 }}>
            Source: {data.source}. {scope === 'season' ? `Season to date over ${periods.length} synced week${periods.length === 1 ? '' : 's'}.` : ''}{' '}
            <span title={data.baseline}>Baseline: projection × games played (hover for detail).</span>
          </p>
        )}
      </section>

      {status === 'loading' && !data && <div className="panel muted">Loading box scores…</div>}
      {status === 'error' && (
        <div className="panel">
          <p className="error">Could not load performers: {error}</p>
        </div>
      )}
      {data && data.contributors.length === 0 && (
        <div className="panel">
          <p className="muted">{data.notes.join(' ') || 'No box scores for this selection yet.'}</p>
        </div>
      )}
      {data && <Explainer unitSizes={data.unit_sizes} benchmarkRates={data.benchmark_rates} categories={data.categories} />}
      {data && data.contributors.length > 0 && (
        <>
          <div className="leaderboards">
            <LeaderboardCard title="Top contributors" tooltip={CONTRIB_TIP} rows={data.contributors} metric="contribution" testId="top-contributors" />
            <LeaderboardCard title="Biggest overperformers" tooltip={OVER_TIP} rows={data.overperformers} metric="over_expected" testId="top-overperformers" />
          </div>
          <section className="panel">
            <div className="panel-head row between">
              <h3>All players</h3>
              <div className="tabs" role="tablist" aria-label="Ranking" style={{ borderBottom: 'none', marginBottom: 0 }}>
                <button type="button" role="tab" aria-selected={metric === 'contribution'} onClick={() => setMetric('contribution')}>
                  By contribution
                </button>
                <button type="button" role="tab" aria-selected={metric === 'over_expected'} onClick={() => setMetric('over_expected')}>
                  By performance vs expected
                </button>
              </div>
            </div>
            <PerformerTable rows={rows} metric={metric} />
            {data.notes.length > 0 && (
              <ul className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                {data.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  )
}
