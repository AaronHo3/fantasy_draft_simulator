import { useMemo, useState } from 'react'
import type { PickView } from '../../api/types'
import { teamColor } from '../../lib/teamColors'
import { useDraftStore } from '../../store/draftStore'
import { CorrectPickDialog } from './CorrectPickDialog'

/** Snake board: one column per manager, team-coloured picks, my column in amber, the live cell outlined. */
export function DraftBoard() {
  const state = useDraftStore((s) => s.state)
  const players = useDraftStore((s) => s.players)
  const pendingCommit = useDraftStore((s) => s.pendingCommit)
  const [correcting, setCorrecting] = useState<number | null>(null)

  const grid = useMemo(() => {
    if (!state) return null
    const order = state.league.draft_order?.length ? state.league.draft_order : state.league.managers.map((m) => m.id)
    const byCell = new Map<string, PickView>()
    let rounds = 0
    for (const p of state.schedule) {
      byCell.set(`${p.round}:${p.manager_id}`, p)
      rounds = Math.max(rounds, p.round)
    }
    const picks = new Map(state.picks.map((p) => [p.overall, p]))
    return { order, byCell, rounds, picks }
  }, [state])

  if (!state || !grid) return null
  const uid = state.league.user_manager_id
  const nameOf = (id: string) => state.league.managers.find((m) => m.id === id)?.name ?? id
  const currentOverall = state.current_pick?.overall ?? null

  return (
    <div>
      <p className="muted small-text" style={{ marginBottom: 8 }}>
        Click a filled cell to correct that pick. Your column is amber; the outlined cell is on the clock. Colour bars are NBA teams.
      </p>
      <div className="board">
        <table aria-label="Draft board">
          <thead>
            <tr>
              <th scope="col" className="round">
                Rd
              </th>
              {grid.order.map((mid) => (
                <th key={mid} scope="col" className={mid === uid ? 'mine' : undefined} title={nameOf(mid)}>
                  {nameOf(mid)}
                  {mid === uid ? ' (you)' : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: grid.rounds }, (_, r) => r + 1).map((round) => (
              <tr key={round}>
                <th scope="row" className="round">
                  {round}
                </th>
                {grid.order.map((mid) => {
                  const sp = grid.byCell.get(`${round}:${mid}`)
                  if (!sp) {
                    return (
                      <td key={mid} className={mid === uid ? 'mine empty' : 'empty'}>
                        —
                      </td>
                    )
                  }
                  const rec = grid.picks.get(sp.overall)
                  const cls = [mid === uid ? 'mine' : '', sp.overall === currentOverall ? 'current' : '', rec ? '' : 'empty'].filter(Boolean).join(' ')
                  const traded = sp.original_manager_id !== sp.manager_id
                  const p = rec ? players[rec.player_id] : null
                  const color = p ? teamColor(p.team).primary : 'transparent'
                  return (
                    <td key={mid} className={cls || undefined} data-testid={`board-cell-${sp.overall}`} data-filled={rec ? 'true' : 'false'} style={rec ? { boxShadow: `inset 3px 0 0 ${color}` } : undefined}>
                      <span className="cell-top">
                        <span>
                          #{sp.overall}
                          {traded ? ` via ${nameOf(sp.original_manager_id)}` : ''}
                          {rec?.is_keeper ? ' keeper' : ''}
                        </span>
                        {p && (
                          <span className="cell-team">
                            {p.team ?? 'FA'} · {p.primary_position ?? ''}
                          </span>
                        )}
                      </span>
                      {rec ? (
                        rec.is_keeper ? (
                          <span className="keeper">{p?.name ?? rec.player_id}</span>
                        ) : (
                          <button type="button" onClick={() => setCorrecting(sp.overall)} aria-label={`Correct pick ${sp.overall}`} disabled={pendingCommit !== null} title={p?.name}>
                            {p?.name ?? rec.player_id}
                          </button>
                        )
                      ) : sp.overall === currentOverall ? (
                        <span className="muted">on the clock</span>
                      ) : (
                        <span className="muted">·</span>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {correcting !== null && <CorrectPickDialog overall={correcting} onClose={() => setCorrecting(null)} />}
    </div>
  )
}
