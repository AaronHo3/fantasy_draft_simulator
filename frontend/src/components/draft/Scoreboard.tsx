import { useShallow } from 'zustand/react/shallow'
import { lastCommittedPick, managerName } from '../../lib/draftState'
import { fmtDate, fmtMs } from '../../lib/format'
import { selectTier, useDraftStore, type SaveStatus } from '../../store/draftStore'
import { Badge, type BadgeTone } from '../common/Badge'
import { Icon } from '../ui/Icon'

const SAVE_TONE: Record<SaveStatus, BadgeTone> = { saved: 'ok', saving: 'accent', offline: 'error', error: 'error' }
const SAVE_TEXT: Record<SaveStatus, string> = { saved: 'saved', saving: 'saving…', offline: 'offline · unsaved pick', error: 'save error' }

/** Charcoal status strip: live state only. Setup lives in Setup, simulation settings in Strategy. */
export function Scoreboard() {
  const state = useDraftStore((s) => s.state)
  const saveStatus = useDraftStore((s) => s.saveStatus)
  const pending = useDraftStore((s) => s.pendingCommit)
  const retry = useDraftStore((s) => s.retryPending)
  const snapshot = useDraftStore((s) => s.snapshot)
  const players = useDraftStore((s) => s.players)
  const tier = useDraftStore(useShallow(selectTier))
  const updateLeague = useDraftStore((s) => s.updateLeague)
  const undoLastPick = useDraftStore((s) => s.undoLastPick)
  if (!state) return null
  const cp = state.current_pick
  const total = state.schedule.length
  const uid = state.league.user_manager_id
  const onClockIsMe = state.on_clock_manager_id === uid
  const last = lastCommittedPick(state)
  const myIndex = state.league.managers.findIndex((m) => m.id === uid)

  const chooseTeam = (id: string) => {
    if (id === uid) return
    const name = managerName(state, id)
    if (!window.confirm(`Set "${name}" as your team? The pick schedule and every recommendation will recompute for that slot.`)) return
    void updateLeague({ ...state.league, user_manager_id: id, managers: state.league.managers.map((m) => ({ ...m, is_user: m.id === id })) })
  }
  const undo = async () => {
    if (!last) return
    const pname = players[last.player_id]?.name ?? last.player_id
    if (!window.confirm(`Undo pick #${last.overall}: ${pname} → ${managerName(state, last.manager_id)}?`)) return
    await undoLastPick()
  }

  return (
    <div className="status-strip" role="region" aria-label="Draft status">
      <div className="cell">
        <span className={state.is_complete ? 'live done' : 'live'} data-testid="top-mode">
          {state.is_complete ? 'DRAFT COMPLETE' : 'LIVE DRAFT'}
        </span>
        <span className="muted" style={{ fontSize: 11 }}>
          {state.league.scoring_format.replace('h2h_', 'H2H ').replace('_', ' ')}{' '}
          <Badge tone={state.format_confirmed ? 'ok' : 'warn'} testId="top-format">
            {state.format_confirmed ? 'confirmed' : 'NOT confirmed'}
          </Badge>
        </span>
      </div>
      <div className="cell">
        <span className="k">Round · pick</span>
        <span className="v big">
          <span data-testid="top-round">{cp ? cp.round : '—'}</span>
          <span className="dim"> · </span>
          <span data-testid="top-overall">{cp ? `${cp.overall} / ${total}` : `complete (${total})`}</span>
        </span>
      </div>
      <div className={onClockIsMe ? 'cell clock me' : 'cell clock'}>
        <span className="k">On the clock</span>
        <span className="v" data-testid="top-on-clock">
          {managerName(state, state.on_clock_manager_id)}
          {onClockIsMe ? ' (you)' : ''}
        </span>
      </div>
      <div className="cell">
        <span className="k">My next pick</span>
        <span className="v">
          <span data-testid="top-my-next">{state.user_next_pick ? `#${state.user_next_pick.overall} (R${state.user_next_pick.round})` : '—'}</span>
          <span className="muted"> · </span>
          <span data-testid="top-picks-until">{state.picks_until_user_turn ?? '—'}</span>
          <span className="muted"> picks away</span>
        </span>
      </div>
      <div className="cell">
        <span className="k">My team</span>
        <select data-testid="top-my-team" aria-label="Which team is mine" value={uid} onChange={(e) => chooseTeam(e.target.value)}>
          {state.league.managers.map((m, i) => (
            <option key={m.id} value={m.id}>
              #{i + 1} {m.name}
            </option>
          ))}
        </select>
      </div>
      <div className="cell grow">
        {last && (
          <button type="button" className="small" data-testid="board-undo" disabled={pending !== null} onClick={() => void undo()} title="Undo the most recent pick">
            <Icon name="undo" size={13} /> Undo #{last.overall} {players[last.player_id]?.name ?? ''}
          </button>
        )}
        <span className="muted" title={`${snapshot?.label ?? ''} · ${snapshot ? fmtDate(snapshot.created_at) : ''}`} style={{ fontSize: 11 }}>
          data {snapshot ? fmtDate(snapshot.created_at).slice(0, 10) : '…'}
          {snapshot?.is_demo && (
            <>
              {' '}
              <Badge tone="loud">DEMO</Badge>
            </>
          )}
        </span>
        <Badge tone={tier.tier === '—' ? 'neutral' : 'accent'} testId="top-tier" title={`${tier.label} · ${fmtMs(tier.computedMs)} · simulation budget ${(state.strategy.sim_budget_ms / 1000).toFixed(1)} s (Strategy tab)`}>
          model {tier.label} · {(state.strategy.sim_budget_ms / 1000).toFixed(1)} s
        </Badge>
        <Badge tone={SAVE_TONE[saveStatus]} testId="top-save-status">
          {SAVE_TEXT[saveStatus]}
        </Badge>
        {pending && saveStatus !== 'saving' && (
          <button type="button" className="small" onClick={() => void retry()}>
            Retry save
          </button>
        )}
        {myIndex < 0 && <Badge tone="error">no team selected</Badge>}
      </div>
    </div>
  )
}
