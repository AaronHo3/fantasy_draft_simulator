import { useSeasonStore } from '../../store/seasonStore'
import { MatchupCard } from './MatchupCard'

export function MatchupsTab({ sessionId, userId }: { sessionId: string; userId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const period = useSeasonStore((s) => s.period)
  const setPeriod = useSeasonStore((s) => s.setPeriod)
  const loadOverview = useSeasonStore((s) => s.loadOverview)
  if (!overview) return null
  const others = overview.matchups.filter((m) => m.home_manager_id !== userId && m.away_manager_id !== userId)
  const periods = Array.from({ length: 22 }, (_, i) => i + 1)
  return (
    <div className="stack">
      <div className="row">
        <label htmlFor="period">Matchup period</label>
        <select
          id="period"
          value={period ?? overview.current_period}
          onChange={(e) => {
            const p = Number(e.target.value)
            setPeriod(p)
            void loadOverview(sessionId, p)
          }}
        >
          {periods.map((p) => (
            <option key={p} value={p}>
              Week {p}
              {p === overview.current_period ? ' (current)' : ''}
            </option>
          ))}
        </select>
      </div>
      {overview.user_matchup ? (
        <MatchupCard pair={overview.user_matchup} names={overview.manager_names} categories={overview.league_categories} userId={userId} />
      ) : (
        <p className="muted">No ESPN pairing for you this period yet.</p>
      )}
      {others.length > 0 && (
        <>
          <h3 style={{ marginTop: 8 }}>Other matchups</h3>
          <div className="matchup-grid">
            {others.map((m) => (
              <MatchupCard key={`${m.home_manager_id}-${m.away_manager_id ?? 'bye'}`} pair={m} names={overview.manager_names} categories={overview.league_categories} userId={userId} compact />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
