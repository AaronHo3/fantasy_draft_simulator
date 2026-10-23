import { Fragment } from 'react'
import { selectRecCurrent, useDraftStore } from '../../store/draftStore'
import { Badge } from '../common/Badge'
import { PlayerName } from '../common/PlayerName'
import { TeamMark } from '../ui/PlayerIdentity'

/** My roster by lineup slot (starters, then bench), legality and what is still needed. */
export function RosterPanel() {
  const state = useDraftStore((s) => s.state)
  const rec = useDraftStore((s) => s.rec)
  const current = useDraftStore(selectRecCurrent)
  const players = useDraftStore((s) => s.players)
  const previewPlayerId = useDraftStore((s) => s.previewPlayerId)
  if (!state) return null
  const uid = state.league.user_manager_id
  const roster = current && rec ? rec.user_roster : null
  const myIds = state.rosters[uid] ?? []

  return (
    <section aria-labelledby="roster-h">
      <div className="panel-head">
        <h3 id="roster-h">Lineup slots{previewPlayerId ? ' (preview)' : ''}</h3>
        <span className="muted small-text">
          {myIds.length} drafted · {state.remaining_user_picks} picks left
        </span>
      </div>
      {roster ? (
        <>
          <ul className="roster-list" aria-label="Roster slots">
            {roster.assignments.map((a, i) => {
              const firstBench = a.slot === 'BENCH' && (i === 0 || roster.assignments[i - 1].slot !== 'BENCH')
              const p = a.player_id ? players[a.player_id] : null
              return (
                <Fragment key={`${a.slot}-${i}`}>
                  {firstBench && <li className="group-head">Bench</li>}
                  <li className={a.slot === 'BENCH' ? 'bench' : undefined}>
                    <span className="slot">{a.slot === 'BENCH' ? 'BN' : a.slot}</span>
                    <span className="who">{a.player_id ? <PlayerName playerId={a.player_id} name={a.name} /> : <span className="empty">open</span>}</span>
                    <span className="side">
                      {p ? (
                        <>
                          <TeamMark team={p.team} /> {p.eligible_positions?.join('/') ?? ''}
                        </>
                      ) : null}
                    </span>
                  </li>
                </Fragment>
              )
            })}
          </ul>
          <div className="row" style={{ marginTop: 10 }}>
            <Badge tone={roster.legal ? 'ok' : 'error'}>{roster.legal ? 'lineup legal' : 'lineup NOT legal'}</Badge>
            <Badge tone={roster.caps_ok ? 'ok' : 'error'}>{roster.caps_ok ? 'caps ok' : `caps violated: ${Object.entries(roster.cap_violations).map(([p, n]) => `${p} +${n}`).join(', ')}`}</Badge>
            <Badge tone={roster.completion_feasible ? 'ok' : 'warn'} title={roster.completion_detail}>
              {roster.completion_feasible ? 'completion feasible' : 'completion at risk'}
            </Badge>
            <span className="muted small-text">coverage {Math.round(roster.coverage_ratio * 100)}%</span>
          </div>
          <div className="needs" aria-label="Positional needs">
            <span className="muted small-text">Still need:</span>
            {roster.open_starting_slots.length === 0 && <span className="badge ok">all starting slots covered</span>}
            {roster.open_starting_slots.map((s, i) => (
              <span key={`${s}-${i}`} className="badge">
                {s}
              </span>
            ))}
            {Object.entries(state.league.position_caps ?? {}).map(([pos, cap]) => {
              const n = myIds.filter((id) => players[id]?.primary_position === pos).length
              return (
                <span key={pos} className={`badge ${n >= cap ? 'warn' : ''}`} title="primary-position cap">
                  {pos} {n}/{cap}
                </span>
              )
            })}
          </div>
          {roster.unassigned.length > 0 && <p className="callout warn">Unassigned (no legal slot): {roster.unassigned.map((id) => players[id]?.name ?? id).join(', ')}</p>}
          {!roster.completion_feasible && <p className="callout warn">{roster.completion_detail}</p>}
        </>
      ) : (
        <>
          <p className="muted">Recalculating slots…</p>
          <ul className="roster-list" aria-label="Drafted players">
            {myIds.map((id) => (
              <li key={id}>
                <span className="slot">{players[id]?.primary_position ?? '?'}</span>
                <span className="who">
                  <PlayerName playerId={id} />
                </span>
                <span className="side" />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
