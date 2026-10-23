import { describe, expect, it } from 'vitest'
import { readHashQuery, withHashQuery } from './hashQuery'

describe('hashQuery', () => {
  it('reads params after the route in the hash', () => {
    expect(readHashQuery('#/season?tab=power&week=3')).toEqual({ tab: 'power', week: '3' })
    expect(readHashQuery('#/season')).toEqual({})
    expect(readHashQuery('')).toEqual({})
  })

  it('writes params without disturbing the route, dropping nulls', () => {
    expect(withHashQuery('#/season?tab=power&week=3', { week: '4', tab: null })).toBe('#/season?week=4')
    expect(withHashQuery('#/performers', { team: 'm05' })).toBe('#/performers?team=m05')
    expect(withHashQuery('#/performers?team=m05', { team: null })).toBe('#/performers')
  })
})
