import { positionsText } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { PlayerName } from '../common/PlayerName'

export function OpponentRosters() {
  const state = useDraftStore((s) => s.state)
  const players = useDraftStore((s) => s.players)
  if (!state) return null
  const uid = state.league.user_manager_id
  return (
    <div className="table-wrap">
      <table className="grid" aria-label="Rosters by manager">
        <thead>
          <tr>
            <th scope="col">Manager</th>
            <th scope="col" className="num">Picks</th>
            <th scope="col">Players (eligible positions)</th>
          </tr>
        </thead>
        <tbody>
          {state.league.managers.map((m) => {
            const ids = state.rosters[m.id] ?? []
            return (
              <tr key={m.id} className={m.id === uid ? 'mine' : undefined}>
                <th scope="row">
                  {m.name}
                  {m.id === uid ? ' (you)' : ''}
                </th>
                <td className="num">{ids.length}</td>
                <td>
                  {ids.map((id, i) => (
                    <span key={id}>
                      {i > 0 ? ', ' : ''}
                      <PlayerName playerId={id} /> <span className="muted">({positionsText(players[id]?.eligible_positions)})</span>
                    </span>
                  ))}
                  {ids.length === 0 && <span className="muted">—</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
