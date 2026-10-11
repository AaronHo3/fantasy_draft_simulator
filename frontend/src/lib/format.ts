import type { CandidateView, CategoryDef } from '../api/types'

export const CATEGORY_KEYS = ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'FG_PCT', 'FT_PCT', 'TOV'] as const
export type CategoryKey = (typeof CATEGORY_KEYS)[number]

export const PER_GAME_KEYS = ['MIN', 'GP', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'FG3A', 'FGM', 'FGA', 'FTM', 'FTA', 'TOV'] as const

export const SLOT_OPTIONS = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL'] as const
export const PRIMITIVE_POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C'] as const

export const RATE_KEYS = new Set(['FG_PCT', 'FT_PCT'])
export const LOWER_IS_BETTER = new Set(['TOV'])

export function isRate(key: string): boolean {
  return RATE_KEYS.has(key)
}

export function categoryLabel(key: string, categories?: CategoryDef[]): string {
  return categories?.find((c) => c.key === key)?.label ?? key
}

export function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return Math.round(n).toLocaleString()
}

/** Rates 0–1 shown like .463 */
export function fmtRate(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(3).replace(/^0/, '')
}

export function fmtSigned(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const s = n.toFixed(digits)
  return n > 0 ? `+${s}` : s
}

export function fmtCategoryValue(key: string, v: number | null | undefined): string {
  return isRate(key) ? fmtRate(v) : fmtInt(v)
}

export function fmtCategoryDelta(key: string, v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (isRate(key)) {
    const s = v.toFixed(3).replace(/^(-?)0/, '$1')
    return v > 0 ? `+${s}` : s
  }
  return fmtSigned(v, 0)
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  return `${Math.round(ms)} ms`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
}

export function fmtPct(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return '—'
  return `${Math.round(p * 100)}%`
}

/** Top-n positive and negative category contributions of a candidate, for the shortlist row. */
export function topContributions(c: CandidateView, n = 2): { gains: string[]; costs: string[] } {
  const entries = Object.entries(c.contributions)
  const gains = entries
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([k, v]) => `${k} ${fmtSigned(v, 1)}`)
  const costs = entries
    .filter(([, v]) => v < 0)
    .sort((a, b) => a[1] - b[1])
    .slice(0, n)
    .map(([k, v]) => `${k} ${fmtSigned(v, 1)}`)
  return { gains, costs }
}

export function positionsText(p: string[] | null | undefined): string {
  return p && p.length ? p.join('/') : '—'
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
