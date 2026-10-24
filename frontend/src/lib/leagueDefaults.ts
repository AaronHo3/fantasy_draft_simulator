import type { CategoryDef, LeagueConfig, Manager } from '../api/types'

export const DEFAULT_NINE_CATEGORIES: CategoryDef[] = [
  { key: 'PTS', label: 'Points', higher_is_better: true, kind: 'counting' },
  { key: 'REB', label: 'Rebounds', higher_is_better: true, kind: 'counting' },
  { key: 'AST', label: 'Assists', higher_is_better: true, kind: 'counting' },
  { key: 'STL', label: 'Steals', higher_is_better: true, kind: 'counting' },
  { key: 'BLK', label: 'Blocks', higher_is_better: true, kind: 'counting' },
  { key: 'FG3M', label: 'Threes made', higher_is_better: true, kind: 'counting' },
  { key: 'FG_PCT', label: 'FG%', higher_is_better: true, kind: 'ratio', numerator: 'FGM', denominator: 'FGA' },
  { key: 'FT_PCT', label: 'FT%', higher_is_better: true, kind: 'ratio', numerator: 'FTM', denominator: 'FTA' },
  { key: 'TOV', label: 'Turnovers', higher_is_better: false, kind: 'counting' },
]

export const DEFAULT_STARTING_SLOTS = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL', 'UTIL', 'UTIL']

export const SCORING_FORMAT_LABELS: Record<LeagueConfig['scoring_format'], string> = {
  h2h_most_categories: 'Head-to-head: most categories',
  h2h_each_category: 'Head-to-head: each category',
  roto: 'Rotisserie',
}

export function managerId(i: number): string {
  return `m${String(i + 1).padStart(2, '0')}`
}

/** Resize the manager list, keeping existing names, and keep exactly one `is_user`. */
export function resizeManagers(existing: Manager[], n: number, userId: string): Manager[] {
  const out: Manager[] = []
  for (let i = 0; i < n; i += 1) {
    const prev = existing[i]
    const id = prev?.id ?? managerId(i)
    out.push({ id, name: prev?.name ?? `Team ${i + 1}`, is_user: id === userId })
  }
  if (!out.some((m) => m.is_user) && out.length > 0) out[0] = { ...out[0], is_user: true }
  return out
}

export function defaultLeague(nManagers = 12, userPosition = 6): LeagueConfig {
  const managers: Manager[] = Array.from({ length: nManagers }, (_, i) => ({
    id: managerId(i),
    name: `Team ${i + 1}`,
    is_user: i + 1 === userPosition,
  }))
  return {
    name: 'My ESPN 9-cat league',
    platform: 'espn',
    season: '2026-27',
    scoring_format: 'h2h_each_category',
    format_confirmed: false,
    categories: DEFAULT_NINE_CATEGORIES,
    tie_rule: { each_category_tie_value: 0.5, matchup_tie_breaker: 'none', zero_attempts: 'unknown' },
    managers,
    user_manager_id: managerId(userPosition - 1),
    starting_slots: DEFAULT_STARTING_SLOTS,
    bench_slots: 3,
    ir_slots: 1,
    draft_type: 'snake',
    draft_order: managers.map((m) => m.id),
    third_round_reversal: false,
    keepers: [],
    traded_picks: [],
    position_caps: { C: 4 },
    position_minimums: {},
    lineup_mode: 'weekly',
    max_games_per_week: null,
    regular_season_weeks: 19,
    playoff_weeks: 3,
    strict_eligibility: false,
  }
}

export function validateLeague(l: LeagueConfig): string[] {
  const errs: string[] = []
  if (!l.name.trim()) errs.push('League name is required.')
  if (l.managers.length < 2) errs.push('A league needs at least two managers.')
  if (l.managers.some((m) => !m.name.trim())) errs.push('Every manager needs a name.')
  if (!l.managers.some((m) => m.id === l.user_manager_id)) errs.push('Pick which team is yours.')
  if (!l.starting_slots || l.starting_slots.length === 0) errs.push('Add at least one starting slot.')
  if (!l.categories || l.categories.length === 0) errs.push('Score at least one category.')
  for (const k of l.keepers ?? []) {
    if (!k.player_id.trim()) errs.push('Keeper rows need a player id.')
    if (k.round < 1 || k.round > (l.starting_slots?.length ?? 0) + l.bench_slots) errs.push(`Keeper round ${k.round} is outside the draft.`)
  }
  for (const t of l.traded_picks ?? []) {
    if (t.from_manager_id === t.to_manager_id) errs.push(`Traded pick in round ${t.round} has the same manager on both sides.`)
  }
  return errs
}
