import { useEffect, useState } from 'react'
import type { MatchupPairView } from '../../api/types'
import { useSeasonStore } from '../../store/seasonStore'
import { Icon } from '../ui/Icon'
import { EmptyState } from '../ui/States'
import { useDraftStore } from '../../store/draftStore'
import { ChartFrame } from '../ui/ChartFrame'
import { MatchupCard } from './MatchupCard'
import { RosterMoves } from './RosterMoves'

const key = (m: MatchupPairView) => `${m.period}:${m.home_manager_id}`
const PERIODS = Array.from({ length: 22 }, (_, i) => i + 1)

/** The featured card is mine by default; clicking any other card swaps it into the main frame. */
export function MatchupsTab({ sessionId, userId }: { sessionId: string; userId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const results = useSeasonStore((s) => s.results)
  const setPeriod = useSeasonStore((s) => s.setPeriod)
  const loadOverview = useSeasonStore((s) => s.loadOverview)
  const loadResults = useSeasonStore((s) => s.loadResults)
  const moves = useSeasonStore((s) => s.moves)
  const movesStatus = useSeasonStore((s) => s.movesStatus)
  const movesError = useSeasonStore((s) => s.movesError)
  const loadMoves = useSeasonStore((s) => s.loadMoves)
  const openDrawer = useDraftStore((s) => s.openDrawer)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const period = overview?.current_period ?? null
  const synced = Boolean(overview?.synced_at)

  // ESPN running totals for the shown week, so the featured card can show actuals beside the odds.
  useEffect(() => {
    if (synced && period !== null) void loadResults(sessionId, period)
  }, [sessionId, period, synced, loadResults])
  useEffect(() => {
    if (synced && period !== null) void loadMoves(sessionId, period)
  }, [sessionId, period, synced, loadMoves])

  if (!overview) return null
  const mine = overview.matchups.find((m) => m.home_manager_id === userId || m.away_manager_id === userId) ?? null
  const featured = overview.matchups.find((m) => key(m) === selectedKey) ?? mine ?? overview.matchups[0] ?? null
  const others = overview.matchups.filter((m) => m !== featured)
  const label = (m: MatchupPairView) => {
    const home = overview.manager_names[m.home_manager_id] ?? m.home_manager_id
    return m.away_manager_id ? `${home} vs ${overview.manager_names[m.away_manager_id] ?? m.away_manager_id}` : `${home} (bye)`
  }
  const actualFor = (m: MatchupPairView) =>
    results && results.period === m.period ? results.results.find((r) => r.home.manager_id === m.home_manager_id || r.away?.manager_id === m.home_manager_id) ?? null : null
  return (
    <div className="stack">
      <div className="filter-bar">
        <span className="field">
          <label htmlFor="period">Week</label>
          <select
            id="period"
            value={overview.current_period}
            onChange={(e) => {
              const p = Number(e.target.value)
              setPeriod(p)
              setSelectedKey(null)
              void loadOverview(sessionId, p)
            }}
          >
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                Week {p}
                {p === overview.current_period ? ' (current)' : ''}
              </option>
            ))}
          </select>
        </span>
        {featured && mine && featured !== mine && (
          <button type="button" className="small" onClick={() => setSelectedKey(null)}>
            <Icon name="chevron-left" size={13} /> Back to my matchup
          </button>
        )}
        <span className="status">{others.length + (featured ? 1 : 0)} pairings · click a card to feature it</span>
      </div>
      {featured ? (
        <div data-testid="featured-matchup" className="featured">
          <MatchupCard pair={featured} names={overview.manager_names} categories={overview.league_categories} userId={userId} actual={actualFor(featured)} />
        </div>
      ) : (
        <EmptyState title="No ESPN pairings for this week yet">Sync after ESPN publishes the schedule for this matchup period.</EmptyState>
      )}
      {moves && moves.period === overview.current_period && (
        <ChartFrame
          title={`Roster moves in week ${overview.current_period}`}
          description="Every add, drop and trade ESPN recorded this matchup period, from the synced transaction log. Your team is listed first."
          legend={[
            { label: 'added', swatch: 'good' },
            { label: 'dropped', swatch: 'bad' },
          ]}
          testId="roster-moves"
        >
          <RosterMoves period={overview.current_period} moves={moves.moves} userId={userId} onOpen={openDrawer} />
        </ChartFrame>
      )}
      {!moves && movesStatus === 'loading' && <p className="muted small-text">Loading roster moves…</p>}
      {movesStatus === 'error' && <p className="error small-text">Roster moves unavailable: {movesError}</p>}
      {others.length > 0 && (
        <>
          <div className="section-title">
            <h2>Other matchups</h2>
            <span className="muted">click one to feature it</span>
          </div>
          <div className="matchup-grid" data-testid="other-matchups">
            {others.map((m) => (
              <div
                key={key(m)}
                role="button"
                tabIndex={0}
                aria-label={`Feature ${label(m)}`}
                className="matchup-pick"
                onClick={() => setSelectedKey(key(m))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setSelectedKey(key(m))
                  }
                }}
              >
                <MatchupCard pair={m} names={overview.manager_names} categories={overview.league_categories} userId={userId} compact />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
