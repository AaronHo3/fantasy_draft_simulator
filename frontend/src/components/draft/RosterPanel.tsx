import { selectRecCurrent, useDraftStore } from '../../store/draftStore'
import { Badge } from '../common/Badge'
import { PlayerName } from '../common/PlayerName'

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
        <h3 id="roster-h">Slots{previewPlayerId ? ' (preview)' : ''}</h3>
        <span className="muted">
          {myIds.length} drafted · {state.remaining_user_picks} picks left
        </span>
      </div>
      {roster ? (
        <>
          <ul className="roster-list" aria-label="Roster slots">
            {roster.assignments.map((a, i) => (
              <li key={`${a.slot}-${i}`} className={a.slot === 'BENCH' ? 'bench' : undefined}>
                <span className="slot">{a.slot === 'BENCH' ? 'BN' : a.slot}</span>
                <span className="who">{a.player_id ? <PlayerName playerId={a.player_id} name={a.name} /> : <span className="empty">open</span>}</span>
                <span className="side">{a.player_id ? `${players[a.player_id]?.team ?? ''} ${players[a.player_id]?.eligible_positions?.join('/') ?? ''}` : ''}</span>
              </li>
            ))}
          </ul>
          <div className="row" style={{ marginTop: 6 }}>
            <Badge tone={roster.legal ? 'ok' : 'error'}>{roster.legal ? 'lineup legal' : 'lineup NOT legal'}</Badge>
            <Badge tone={roster.caps_ok ? 'ok' : 'error'}>{roster.caps_ok ? 'caps ok' : `caps violated: ${Object.entries(roster.cap_violations).map(([p, n]) => `${p} +${n}`).join(', ')}`}</Badge>
            <Badge tone={roster.completion_feasible ? 'ok' : 'warn'} title={roster.completion_detail}>
              {roster.completion_feasible ? 'completion feasible' : 'completion at risk'}
            </Badge>
            <span className="muted">coverage {Math.round(roster.coverage_ratio * 100)}%</span>
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
                <span key={pos} className={`badge ${n >= cap ? 'warn' : ''}`} title={`primary-position cap`}>
                  {pos} {n}/{cap}
                </span>
              )
            })}
          </div>
          {roster.unassigned.length > 0 && (
            <p className="callout warn">Unassigned (no legal slot): {roster.unassigned.map((id) => players[id]?.name ?? id).join(', ')}</p>
          )}
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
