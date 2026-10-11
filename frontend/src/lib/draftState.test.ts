import { describe, expect, it } from 'vitest'
import { makeState } from '../test/fixtures'
import { applyLocalPick, deriveFromPicks, lastCommittedPick, LocalCommitError, removeLastLocalPick, userIsOnClock } from './draftState'

describe('optimistic pick application', () => {
  it('advances the clock, greys the player and bumps the revision like the server will', () => {
    const s0 = makeState()
    const s1 = applyLocalPick(s0, { player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    expect(s1).not.toBe(s0)
    expect(s0.picks).toHaveLength(0) // input untouched
    expect(s1.picks).toHaveLength(1)
    expect(s1.drafted_player_ids).toEqual(['demo:0001'])
    expect(s1.rosters.m01).toEqual(['demo:0001'])
    expect(s1.current_pick?.overall).toBe(2)
    expect(s1.on_clock_manager_id).toBe('m02')
    expect(s1.picks_until_user_turn).toBe(4)
    expect(s1.user_next_pick?.overall).toBe(6)
    expect(s1.last_seq).toBe(s0.last_seq + 1)
    expect(s1.draft_revision).toBe(s0.last_seq + 1)
    expect(s1.strategy_revision).toBe(s0.strategy_revision)
  })

  it('puts the user on the clock after five opponent picks and tracks remaining picks', () => {
    let s = makeState()
    for (let i = 1; i <= 5; i += 1) s = applyLocalPick(s, { player_id: `demo:000${i}`, overall: i, manager_id: `m0${i}` })
    expect(s.on_clock_manager_id).toBe('m06')
    expect(userIsOnClock(s)).toBe(true)
    expect(s.picks_until_user_turn).toBe(0)
    expect(s.remaining_user_picks).toBe(13)
    const s6 = applyLocalPick(s, { player_id: 'demo:0006', overall: 6, manager_id: 'm06' })
    expect(s6.remaining_user_picks).toBe(12)
    expect(s6.user_next_pick?.overall).toBe(19) // snake: 12 teams, 6th pick -> 19th overall
    expect(s6.picks_until_user_turn).toBe(12)
  })

  it('rejects the same errors the server would, with matching codes', () => {
    const s = applyLocalPick(makeState(), { player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    expect(() => applyLocalPick(s, { player_id: 'demo:0001', overall: 2, manager_id: 'm02' })).toThrowError(LocalCommitError)
    try {
      applyLocalPick(s, { player_id: 'demo:0001', overall: 2, manager_id: 'm02' })
    } catch (e) {
      expect((e as LocalCommitError).code).toBe('duplicate_player')
    }
    try {
      applyLocalPick(s, { player_id: 'demo:0002', overall: 2, manager_id: 'm09' })
    } catch (e) {
      expect((e as LocalCommitError).code).toBe('wrong_manager')
    }
    try {
      applyLocalPick(s, { player_id: 'demo:0002', overall: 5, manager_id: 'm05' })
    } catch (e) {
      expect((e as LocalCommitError).code).toBe('not_on_clock')
    }
  })

  it('rollback restores the exact previous state and removing the last pick re-derives', () => {
    const s0 = makeState()
    const s1 = applyLocalPick(s0, { player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    // Rollback is "use the previous object": nothing was mutated.
    expect(s0.current_pick?.overall).toBe(1)
    expect(s0.drafted_player_ids).toEqual([])
    const back = removeLastLocalPick(s1)
    expect(back.picks).toEqual([])
    expect(back.current_pick?.overall).toBe(1)
    expect(lastCommittedPick(s1)?.overall).toBe(1)
    expect(lastCommittedPick(back)).toBeNull()
  })

  it('skips keeper picks when deriving the clock and keeps them out of undo', () => {
    const s0 = makeState()
    const keeper = { overall: 2, manager_id: 'm02', player_id: 'demo:0500', is_keeper: true, source: 'keeper', seq: 0 }
    const s = deriveFromPicks(s0, [keeper])
    expect(s.current_pick?.overall).toBe(1)
    const s1 = applyLocalPick(s, { player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    expect(s1.current_pick?.overall).toBe(3)
    expect(lastCommittedPick(s)).toBeNull()
    expect(s1.is_complete).toBe(false)
  })
})
