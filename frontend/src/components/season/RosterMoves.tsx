import type { RosterMoveView } from '../../api/types'
import { fmtDate, positionsText } from '../../lib/format'
import { Badge } from '../common/Badge'
import { Icon } from '../ui/Icon'
import { PlayerIdentity } from '../ui/PlayerIdentity'
import { EmptyState } from '../ui/States'

interface RosterMovesProps {
  period: number
  moves: RosterMoveView[]
  userId: string
  onOpen?: (playerId: string) => void
}

/** Adds and drops for one matchup period, grouped by team; trades are marked on both sides. */
export function RosterMoves({ period, moves, userId, onOpen }: RosterMovesProps) {
  if (moves.length === 0) return <EmptyState title={`No roster moves in week ${period}`}>Adds, drops and trades appear here after each sync.</EmptyState>
  const byTeam = new Map<string, { name: string; moves: RosterMoveView[] }>()
  for (const m of moves) {
    const g = byTeam.get(m.manager_id) ?? { name: m.manager_name, moves: [] }
    g.moves.push(m)
    byTeam.set(m.manager_id, g)
  }
  const groups = [...byTeam.entries()].sort((a, b) => (a[0] === userId ? -1 : b[0] === userId ? 1 : a[1].name.localeCompare(b[1].name)))
  return (
    <div className="moves-grid">
      {groups.map(([id, g]) => {
        const adds = g.moves.filter((m) => m.kind === 'add')
        const drops = g.moves.filter((m) => m.kind === 'drop')
        return (
          <section key={id} className={`moves-team${id === userId ? ' mine' : ''}`} role="group" aria-label={`${g.name} moves`}>
            <h3>
              {g.name}
              {id === userId ? ' (you)' : ''} <span className="muted">+{adds.length} −{drops.length}</span>
            </h3>
            <ul className="moves-list">
              {[...adds, ...drops].map((m) => (
                <li key={`${m.kind}-${m.player.player_id}-${m.effective_at}`} className={`move ${m.kind}`} title={`${m.kind === 'add' ? 'added' : 'dropped'} ${fmtDate(m.effective_at)} · ${m.source}`}>
                  <span className={`move-sign ${m.kind}`} aria-label={m.kind === 'add' ? 'added' : 'dropped'}>
                    <Icon name={m.kind === 'add' ? 'arrow-up' : 'arrow-down'} size={13} />
                  </span>
                  {onOpen ? (
                    <button type="button" className="player-link" onClick={() => onOpen(m.player.player_id)}>
                      <PlayerIdentity name={m.player.name} team={m.player.team} positions={m.player.eligible_positions} espnId={m.player.espn_id} size={28} />
                    </button>
                  ) : (
                    <PlayerIdentity name={m.player.name} team={m.player.team} positions={m.player.eligible_positions} espnId={m.player.espn_id} size={28} />
                  )}
                  <span className="move-meta muted">
                    {fmtDate(m.effective_at).slice(5, 10)}
                    {m.trade && (
                      <>
                        {' '}
                        <Badge tone="accent">trade</Badge>
                      </>
                    )}
                  </span>
                  <span className="visually-hidden">{positionsText(m.player.eligible_positions)}</span>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
