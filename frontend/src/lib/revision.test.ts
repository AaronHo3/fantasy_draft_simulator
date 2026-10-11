import { describe, expect, it } from 'vitest'
import { acceptIfCurrent, coerceIds, idsMatch } from './revision'

const state = { draft_revision: 7, strategy_revision: 3, league_revision: 1 }

describe('revision guard', () => {
  it('accepts a result whose ids match every revision', () => {
    const res = { ids: { ...state, last_seq: 9, snapshot_id: 's', projection_version: 'p', seed: 1 }, payload: 'ok' }
    expect(idsMatch(res.ids, state)).toBe(true)
    expect(acceptIfCurrent(res, state)).toBe(res)
  })

  it('drops a result computed for an older draft revision', () => {
    const res = { ids: { ...state, draft_revision: 6 } }
    expect(acceptIfCurrent(res, state)).toBeNull()
  })

  it('drops a result when only the strategy revision differs', () => {
    expect(acceptIfCurrent({ ids: { ...state, strategy_revision: 2 } }, state)).toBeNull()
  })

  it('drops a result when only the league revision differs', () => {
    expect(acceptIfCurrent({ ids: { ...state, league_revision: 2 } }, state)).toBeNull()
  })

  it('never treats a result as current when there is no state', () => {
    expect(acceptIfCurrent({ ids: state }, null)).toBeNull()
    expect(idsMatch(undefined, state)).toBe(false)
  })

  it('coerces loose job ids and rejects malformed ones', () => {
    expect(coerceIds({ draft_revision: 1, strategy_revision: 2, league_revision: 3, extra: 'x' })).toEqual({ draft_revision: 1, strategy_revision: 2, league_revision: 3 })
    expect(coerceIds({ draft_revision: '1', strategy_revision: 2, league_revision: 3 })).toBeNull()
    expect(coerceIds(null)).toBeNull()
  })
})
