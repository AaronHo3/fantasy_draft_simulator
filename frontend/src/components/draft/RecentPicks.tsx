import { useState } from 'react'
import { managerName } from '../../lib/draftState'
import { teamColor } from '../../lib/teamColors'
import { useDraftStore } from '../../store/draftStore'
import { PlayerName } from '../common/PlayerName'
import { CorrectPickDialog } from './CorrectPickDialog'

/** Most recent picks first; click "fix" to correct a wrongly recorded player. */
export function RecentPicks({ limit = 24 }: { limit?: number }) {
  const state = useDraftStore((s) => s.state)
  const players = useDraftStore((s) => s.players)
  const pendingCommit = useDraftStore((s) => s.pendingCommit)
  const [correcting, setCorrecting] = useState<number | null>(null)
  if (!state) return null
  const uid = state.league.user_manager_id
  const picks = [...state.picks].sort((a, b) => b.overall - a.overall).slice(0, limit)
  const byOverall = new Map(state.schedule.map((p) => [p.overall, p]))
  if (picks.length === 0) {
    return (
      <div className="empty-state" data-testid="recent-empty">
        <b>No picks recorded yet.</b> When the first player comes off the board, find them in the picker and record the pick.
      </div>
    )
  }
  return (
    <>
      <ul className="recent-list" aria-label="Recent picks" data-testid="recent-picks">
        {picks.map((p) => {
          const sp = byOverall.get(p.overall)
          return (
            <li key={p.overall} className={p.manager_id === uid ? 'mine' : undefined} data-testid="recent-pick" data-overall={p.overall} style={{ borderLeftColor: teamColor(players[p.player_id]?.team).primary }}>
              <span className="pick-no">
                #{p.overall}
                <br />
                R{sp?.round ?? '?'}.{sp?.pick_in_round ?? '?'}
              </span>
              <span>
                <PlayerName playerId={p.player_id} />
                <br />
                <span className="team">
                  {managerName(state, p.manager_id)}
                  {p.is_keeper ? ' · keeper' : ''}
                  {p.source === 'import' ? ' · imported' : ''}
                </span>
              </span>
              {!p.is_keeper && (
                <button type="button" className="small ghost" onClick={() => setCorrecting(p.overall)} disabled={pendingCommit !== null} aria-label={`Correct pick ${p.overall}`}>
                  fix
                </button>
              )}
            </li>
          )
        })}
      </ul>
      {correcting !== null && <CorrectPickDialog overall={correcting} onClose={() => setCorrecting(null)} />}
    </>
  )
}
