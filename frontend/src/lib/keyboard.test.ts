import { describe, expect, it } from 'vitest'
import { initialPickerState, pickerReducer, type PickerRow, type PickerState } from './keyboard'

const rows: PickerRow[] = [
  { id: 'a', disabled: true }, // drafted
  { id: 'b', disabled: false },
  { id: 'c', disabled: false },
  { id: 'd', disabled: true },
  { id: 'e', disabled: false },
]

function withRows(): PickerState {
  return pickerReducer(initialPickerState, { type: 'rows', rows })
}

describe('picker keyboard reducer', () => {
  it('starts on the first non-drafted row when results arrive', () => {
    expect(withRows().cursor).toBe(1)
  })

  it('moves with arrows, skipping drafted rows and clamping at the ends', () => {
    let s = withRows()
    s = pickerReducer(s, { type: 'move', delta: 1 })
    expect(s.cursor).toBe(2)
    s = pickerReducer(s, { type: 'move', delta: 1 })
    expect(s.cursor).toBe(4) // skipped 'd'
    s = pickerReducer(s, { type: 'move', delta: 1 })
    expect(s.cursor).toBe(4) // clamped
    s = pickerReducer(s, { type: 'move', delta: -1 })
    s = pickerReducer(s, { type: 'move', delta: -1 })
    s = pickerReducer(s, { type: 'move', delta: -1 })
    expect(s.cursor).toBe(1) // never lands on the drafted 'a'
  })

  it('Enter opens the confirm step with the on-clock manager preselected, Enter again is a no-op here, Esc cancels', () => {
    let s = withRows()
    s = pickerReducer(s, { type: 'enter', defaultManagerId: 'm03' })
    expect(s.stage).toBe('confirm')
    expect(s.selectedId).toBe('b')
    expect(s.managerId).toBe('m03')
    const again = pickerReducer(s, { type: 'enter', defaultManagerId: 'm03' })
    expect(again).toBe(s) // the component commits on the second Enter; the reducer does not change
    s = pickerReducer(s, { type: 'manager', managerId: 'm05' })
    expect(s.managerId).toBe('m05')
    s = pickerReducer(s, { type: 'escape' })
    expect(s.stage).toBe('browse')
    expect(s.selectedId).toBeNull()
    expect(s.cursor).toBe(1)
  })

  it('does not open the confirm step on a drafted row and ignores moves while confirming', () => {
    const s = { ...withRows(), cursor: 0 }
    expect(pickerReducer(s, { type: 'enter', defaultManagerId: 'm01' }).stage).toBe('browse')
    const confirming = pickerReducer(withRows(), { type: 'enter', defaultManagerId: 'm01' })
    expect(pickerReducer(confirming, { type: 'move', delta: 1 }).cursor).toBe(confirming.cursor)
  })

  it('keeps the cursor on the same player when results refresh, and relocates when it got drafted', () => {
    let s = withRows()
    s = pickerReducer(s, { type: 'move', delta: 1 }) // on 'c'
    const reordered: PickerRow[] = [{ id: 'c', disabled: false }, { id: 'b', disabled: false }]
    s = pickerReducer(s, { type: 'rows', rows: reordered })
    expect(s.cursor).toBe(0)
    const cDrafted: PickerRow[] = [{ id: 'c', disabled: true }, { id: 'b', disabled: false }]
    s = pickerReducer(s, { type: 'rows', rows: cDrafted })
    expect(s.cursor).toBe(1)
  })

  it('select by click opens confirm unless the row is drafted; committed returns to browse', () => {
    let s = withRows()
    expect(pickerReducer(s, { type: 'select', id: 'a', defaultManagerId: 'm01' }).stage).toBe('browse')
    s = pickerReducer(s, { type: 'select', id: 'e', defaultManagerId: 'm01' })
    expect(s.stage).toBe('confirm')
    expect(s.cursor).toBe(4)
    s = pickerReducer(s, { type: 'committed' })
    expect(s.stage).toBe('browse')
    expect(s.selectedId).toBeNull()
  })
})
