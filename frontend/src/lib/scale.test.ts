import { describe, expect, it } from 'vitest'
import { linear, niceMax, probabilityTone, symmetricMax } from './scale'

describe('scale helpers', () => {
  it('maps a domain onto a range linearly and clamps', () => {
    const s = linear([0, 10], [0, 100])
    expect(s(5)).toBe(50)
    expect(s(12)).toBe(100)
    expect(s(-1)).toBe(0)
  })

  it('rounds a maximum up to a readable number', () => {
    expect(niceMax(7.3)).toBe(8)
    expect(niceMax(63)).toBe(70)
    expect(niceMax(0)).toBe(1)
  })

  it('finds a symmetric extent around zero', () => {
    expect(symmetricMax([-3, 2, 8])).toBe(8)
    expect(symmetricMax([])).toBe(1)
  })

  it('classifies a win probability into a tone and keeps 50% neutral', () => {
    expect(probabilityTone(0.5)).toBe('even')
    expect(probabilityTone(0.72)).toBe('good')
    expect(probabilityTone(0.2)).toBe('bad')
  })
})
