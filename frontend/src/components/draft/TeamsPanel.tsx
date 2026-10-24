import { useState } from 'react'
import { positionsText } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { useSeasonStore } from '../../store/seasonStore'
import { PlayerName } from '../common/PlayerName'

/** Inspect any manager's roster without leaving my own context (my roster stays in its own tab). */
export function TeamsPanel() {
  const state = useDraftStore((s) => s.state)
  const players = useDraftStore((s) => s.players)
  const moves = useSeasonStore((s) => s.moves)
  const [selected, setSelected] = useState<string | null>(null)
  if (!state) return null
  const addedThisWeek = new Set((moves?.moves ?? []).filter((m) => m.kind === 'add' && m.period === moves?.period).map((m) => `${m.manager_id}:${m.player.player_id}`))
  const uid = state.league.user_manager_id
  const onClock = state.on_clock_manager_id
  const mid = selected ?? onClock ?? state.league.managers[0]?.id ?? null
  const m = state.league.managers.find((x) => x.id === mid)
  const drafted = mid ? state.rosters[mid] ?? [] : []
  const ids = mid ? (state.has_roster_moves ? state.current_rosters[mid] ?? drafted : drafted) : []
  const added = new Set(ids.filter((id) => !drafted.includes(id)))
  const counts: Record<string, number> = {}
  for (const id of ids) {
    const pp = players[id]?.primary_position ?? '?'
    counts[pp] = (counts[pp] ?? 0) + 1
  }
  const caps = state.league.position_caps ?? {}
  return (
    <div>
      <div className="row" style={{ marginBottom: 6 }}>
        <label htmlFor="teams-select">Team</label>
        <select id="teams-select" value={mid ?? ''} onChange={(e) => setSelected(e.target.value)} data-testid="teams-select">
          {state.league.managers.map((x, i) => (
            <option key={x.id} value={x.id}>
              #{i + 1} {x.name}
              {x.id === uid ? ' (you)' : ''}
              {x.id === onClock ? ' · on the clock' : ''}
            </option>
          ))}
        </select>
        <span className="muted">
          {ids.length} drafted · {state.schedule.filter((p) => p.manager_id === mid && !state.picks.some((q) => q.overall === p.overall)).length} picks left
        </span>
      </div>
      {m && (
        <>
          <div className="needs" aria-label="Primary position counts">
            {['PG', 'SG', 'SF', 'PF', 'C'].map((p) => (
              <span key={p} className={`badge ${caps[p] !== undefined && (counts[p] ?? 0) >= caps[p] ? 'warn' : ''}`} title={caps[p] !== undefined ? `cap ${caps[p]}` : undefined}>
                {p} {counts[p] ?? 0}
                {caps[p] !== undefined ? `/${caps[p]}` : ''}
              </span>
            ))}
          </div>
          {ids.length === 0 ? (
            <p className="muted" style={{ marginTop: 8 }}>
              No players yet.
            </p>
          ) : (
            <ul className="roster-list" style={{ marginTop: 8 }} aria-label={`${m.name} roster`}>
              {ids.map((id, i) => (
                <li key={id}>
                  <span className="slot">{i + 1}</span>
                  <span className="who">
                    <PlayerName playerId={id} />
                    {added.has(id) && (
                      <span className={addedThisWeek.has(`${mid}:${id}`) ? 'badge ok' : 'badge accent'} title={addedThisWeek.has(`${mid}:${id}`) ? `added in week ${moves?.period} (ESPN sync)` : 'added after the draft (ESPN sync)'}>
                        {addedThisWeek.has(`${mid}:${id}`) ? `added wk ${moves?.period}` : 'added'}
                      </span>
                    )}
                  </span>
                  <span className="side">
                    {players[id]?.team ?? '—'} · {positionsText(players[id]?.eligible_positions)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <p className="muted small-text" style={{ marginTop: 8 }}>
        Category totals and ranks for every team are in "League category profiles" under the draft history.
      </p>
    </div>
  )
}
