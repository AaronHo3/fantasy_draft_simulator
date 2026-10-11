// Pure reducer for the player picker's keyboard flow:
//   browse (↑/↓ move, Enter opens confirm) -> confirm (Enter commits, Esc cancels) -> browse.

export interface PickerRow {
  id: string
  disabled: boolean // drafted players cannot be selected
}

export type PickerStage = 'browse' | 'confirm'

export interface PickerState {
  rows: PickerRow[]
  cursor: number // -1 when nothing is highlighted
  stage: PickerStage
  selectedId: string | null
  managerId: string | null
}

export type PickerAction =
  | { type: 'rows'; rows: PickerRow[] }
  | { type: 'move'; delta: 1 | -1 }
  | { type: 'hover'; index: number }
  | { type: 'enter'; defaultManagerId: string | null }
  | { type: 'select'; id: string; defaultManagerId: string | null }
  | { type: 'manager'; managerId: string }
  | { type: 'escape' }
  | { type: 'committed' }

export const initialPickerState: PickerState = { rows: [], cursor: -1, stage: 'browse', selectedId: null, managerId: null }

function firstEnabled(rows: PickerRow[], from: number, step: 1 | -1): number {
  for (let i = from; i >= 0 && i < rows.length; i += step) if (!rows[i].disabled) return i
  return -1
}

export function pickerReducer(s: PickerState, a: PickerAction): PickerState {
  switch (a.type) {
    case 'rows': {
      // Keep the cursor on the same player when it is still listed; otherwise go to the first enabled row.
      const curId = s.cursor >= 0 ? s.rows[s.cursor]?.id : undefined
      const keep = curId ? a.rows.findIndex((r) => r.id === curId && !r.disabled) : -1
      const cursor = keep >= 0 ? keep : firstEnabled(a.rows, 0, 1)
      return { ...s, rows: a.rows, cursor }
    }
    case 'move': {
      if (s.stage !== 'browse' || s.rows.length === 0) return s
      const start = s.cursor < 0 ? (a.delta === 1 ? 0 : s.rows.length - 1) : s.cursor + a.delta
      const next = firstEnabled(s.rows, start, a.delta)
      return next < 0 ? s : { ...s, cursor: next }
    }
    case 'hover': {
      if (a.index < 0 || a.index >= s.rows.length || s.rows[a.index].disabled) return s
      return { ...s, cursor: a.index }
    }
    case 'enter': {
      if (s.stage !== 'browse') return s
      const row = s.cursor >= 0 ? s.rows[s.cursor] : undefined
      if (!row || row.disabled) return s
      return { ...s, stage: 'confirm', selectedId: row.id, managerId: a.defaultManagerId }
    }
    case 'select': {
      const row = s.rows.find((r) => r.id === a.id)
      if (row?.disabled) return s
      const idx = s.rows.findIndex((r) => r.id === a.id)
      return { ...s, cursor: idx >= 0 ? idx : s.cursor, stage: 'confirm', selectedId: a.id, managerId: a.defaultManagerId }
    }
    case 'manager':
      return s.stage === 'confirm' ? { ...s, managerId: a.managerId } : s
    case 'escape':
      return s.stage === 'confirm' ? { ...s, stage: 'browse', selectedId: null, managerId: null } : s
    case 'committed':
      return { ...s, stage: 'browse', selectedId: null, managerId: null }
    default:
      return s
  }
}
