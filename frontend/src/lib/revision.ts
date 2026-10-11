// Revision guard: a recommendation/refinement result is only "current" when its ids match the
// draft, strategy and league revisions of the state the UI is showing.

export interface RevisionIds {
  draft_revision: number
  strategy_revision: number
  league_revision: number
}

export function idsMatch(ids: RevisionIds | null | undefined, state: RevisionIds | null | undefined): boolean {
  if (!ids || !state) return false
  return (
    ids.draft_revision === state.draft_revision &&
    ids.strategy_revision === state.strategy_revision &&
    ids.league_revision === state.league_revision
  )
}

/** Returns the result when it is current for `state`, otherwise null (stale results are dropped). */
export function acceptIfCurrent<T extends { ids: RevisionIds }>(result: T, state: RevisionIds | null): T | null {
  return idsMatch(result.ids, state) ? result : null
}

/** Loose ids (e.g. JobView.ids is a free-form dict) -> typed, or null when malformed. */
export function coerceIds(raw: Record<string, unknown> | null | undefined): RevisionIds | null {
  if (!raw) return null
  const d = raw.draft_revision
  const s = raw.strategy_revision
  const l = raw.league_revision
  if (typeof d !== 'number' || typeof s !== 'number' || typeof l !== 'number') return null
  return { draft_revision: d, strategy_revision: s, league_revision: l }
}
