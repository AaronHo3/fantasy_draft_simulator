import { positionsText } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { useSeasonStore } from '../../store/seasonStore'
import { PlayerName } from '../common/PlayerName'

export function OpponentRosters() {
  const state = useDraftStore((s) => s.state)
  const players = useDraftStore((s) => s.players)
  const moves = useSeasonStore((s) => s.moves)
  if (!state) return null
  const uid = state.league.user_manager_id
  const addedThisWeek = new Set((moves?.moves ?? []).filter((m) => m.kind === 'add' && m.period === moves?.period).map((m) => `${m.manager_id}:${m.player.player_id}`))
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
            const drafted = state.rosters[m.id] ?? []
            const ids = state.has_roster_moves ? state.current_rosters[m.id] ?? drafted : drafted
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
                      <PlayerName playerId={id} />{' '}
                      <span className="muted">
                        ({positionsText(players[id]?.eligible_positions)}
                        {!drafted.includes(id) ? (addedThisWeek.has(`${m.id}:${id}`) ? `, added wk ${moves?.period}` : ', added') : ''})
                      </span>
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
