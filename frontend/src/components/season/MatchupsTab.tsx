import { useState } from 'react'
import type { MatchupPairView } from '../../api/types'
import { useSeasonStore } from '../../store/seasonStore'
import { MatchupCard } from './MatchupCard'

const key = (m: MatchupPairView) => `${m.period}:${m.home_manager_id}`

/** The featured card is mine by default; clicking any other card swaps it into the main frame. */
export function MatchupsTab({ sessionId, userId }: { sessionId: string; userId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const setPeriod = useSeasonStore((s) => s.setPeriod)
  const loadOverview = useSeasonStore((s) => s.loadOverview)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  if (!overview) return null
  const mine = overview.matchups.find((m) => m.home_manager_id === userId || m.away_manager_id === userId) ?? null
  const featured = overview.matchups.find((m) => key(m) === selectedKey) ?? mine ?? overview.matchups[0] ?? null
  const others = overview.matchups.filter((m) => m !== featured)
  const periods = Array.from({ length: 22 }, (_, i) => i + 1)
  const label = (m: MatchupPairView) => {
    const home = overview.manager_names[m.home_manager_id] ?? m.home_manager_id
    return m.away_manager_id ? `${home} vs ${overview.manager_names[m.away_manager_id] ?? m.away_manager_id}` : `${home} (bye)`
  }
  return (
    <div className="stack">
      <div className="row">
        <label htmlFor="period">Matchup period</label>
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
          {periods.map((p) => (
            <option key={p} value={p}>
              Week {p}
              {p === overview.current_period ? ' (current)' : ''}
            </option>
          ))}
        </select>
        {featured && mine && featured !== mine && (
          <button type="button" className="small" onClick={() => setSelectedKey(null)}>
            Back to my matchup
          </button>
        )}
      </div>
      {featured ? (
        <div data-testid="featured-matchup">
          <MatchupCard pair={featured} names={overview.manager_names} categories={overview.league_categories} userId={userId} />
        </div>
      ) : (
        <p className="muted">No ESPN pairings for this period yet.</p>
      )}
      {others.length > 0 && (
        <>
          <h3 style={{ marginTop: 8 }}>Other matchups <span className="muted">(click one to feature it)</span></h3>
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
