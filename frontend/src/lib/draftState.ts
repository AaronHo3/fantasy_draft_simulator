// Pure helpers over DraftStateView: optimistic pick application and derived-field recomputation.
// Nothing here mutates its input; every function returns a new object.
import type { DraftStateView, PickRecordView, PickView } from '../api/types'

export interface LocalPick {
  player_id: string
  overall: number
  manager_id: string
}

export class LocalCommitError extends Error {
  readonly code: string
  constructor(code: string, message: string) {
    super(message)
    this.name = 'LocalCommitError'
    this.code = code
  }
}

function nextPickFor(schedule: PickView[], managerId: string, afterOverall: number, taken: Set<number>): PickView | null {
  for (const p of schedule) {
    if (p.overall > afterOverall && p.manager_id === managerId && !p.keeper_player_id && !taken.has(p.overall)) return p
  }
  return null
}

/** Recompute every derived field of the state from `picks` + the schedule (mirrors backend replay). */
export function deriveFromPicks(state: DraftStateView, picks: PickRecordView[]): DraftStateView {
  const sorted = [...picks].sort((a, b) => a.overall - b.overall)
  const taken = new Set(sorted.map((p) => p.overall))
  const current = state.schedule.find((p) => !taken.has(p.overall)) ?? null
  const uid = state.league.user_manager_id
  let userNext: PickView | null = null
  let userFollowing: PickView | null = null
  if (current) {
    userNext = current.manager_id === uid ? current : nextPickFor(state.schedule, uid, current.overall - 1, taken)
    if (userNext) userFollowing = nextPickFor(state.schedule, uid, userNext.overall, taken)
  }
  const rosters: Record<string, string[]> = {}
  for (const m of state.league.managers) rosters[m.id] = []
  for (const p of sorted) rosters[p.manager_id] = [...(rosters[p.manager_id] ?? []), p.player_id]
  const remainingUser = state.schedule.filter((p) => p.manager_id === uid && !taken.has(p.overall)).length
  return {
    ...state,
    picks: sorted,
    rosters,
    drafted_player_ids: sorted.map((p) => p.player_id).sort(),
    current_pick: current,
    on_clock_manager_id: current?.manager_id ?? null,
    user_next_pick: userNext,
    user_following_pick: userFollowing,
    picks_until_user_turn: current && userNext ? Math.max(0, userNext.overall - current.overall) : null,
    remaining_user_picks: remainingUser,
    is_complete: current === null,
  }
}

/** Apply a pick locally (optimistic). Throws LocalCommitError with the same codes the server uses. */
export function applyLocalPick(state: DraftStateView, pick: LocalPick): DraftStateView {
  const cp = state.current_pick
  if (!cp) throw new LocalCommitError('draft_complete', 'the draft is complete')
  if (pick.overall !== cp.overall) {
    throw new LocalCommitError('not_on_clock', `pick ${pick.overall} is not on the clock (current is ${cp.overall})`)
  }
  if (pick.manager_id !== cp.manager_id) {
    throw new LocalCommitError('wrong_manager', `${cp.manager_id} is on the clock, not ${pick.manager_id}`)
  }
  if (state.drafted_player_ids.includes(pick.player_id)) {
    throw new LocalCommitError('duplicate_player', `${pick.player_id} was already drafted`)
  }
  const record: PickRecordView = {
    overall: pick.overall,
    manager_id: pick.manager_id,
    player_id: pick.player_id,
    is_keeper: false,
    source: 'manual',
    seq: state.last_seq + 1,
  }
  // Mirror the server: the event gets seq = last_seq + 1 and bumps draft_revision to that seq, so any
  // recommendation computed for the previous revision is recognised as stale immediately.
  const bumped: DraftStateView = { ...state, last_seq: state.last_seq + 1, draft_revision: state.last_seq + 1 }
  return deriveFromPicks(bumped, [...state.picks, record])
}

/** Remove the last non-keeper pick locally (used only for display while an undo is in flight). */
export function removeLastLocalPick(state: DraftStateView): DraftStateView {
  const nonKeeper = state.picks.filter((p) => !p.is_keeper)
  if (nonKeeper.length === 0) return state
  const last = nonKeeper.reduce((a, b) => (a.overall > b.overall ? a : b))
  return deriveFromPicks(state, state.picks.filter((p) => p.overall !== last.overall))
}

export function lastCommittedPick(state: DraftStateView): PickRecordView | null {
  const nonKeeper = state.picks.filter((p) => !p.is_keeper)
  if (nonKeeper.length === 0) return null
  return nonKeeper.reduce((a, b) => (a.overall > b.overall ? a : b))
}

export function managerName(state: DraftStateView, managerId: string | null | undefined): string {
  if (!managerId) return '—'
  return state.league.managers.find((m) => m.id === managerId)?.name ?? managerId
}

export function userIsOnClock(state: DraftStateView): boolean {
  return state.on_clock_manager_id !== null && state.on_clock_manager_id === state.league.user_manager_id
}

export function pickLookup(state: DraftStateView): Map<string, PickRecordView> {
  return new Map(state.picks.map((p) => [p.player_id, p]))
}
