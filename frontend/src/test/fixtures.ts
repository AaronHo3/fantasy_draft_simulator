import type { CandidateView, DraftStateView, PickView, RecommendationResponse, ResponseIds } from '../api/types'
import { defaultLeague } from '../lib/leagueDefaults'

/** 12-team snake schedule, user picks 6th, 13 rounds. */
export function makeSchedule(nManagers = 12, rounds = 13): PickView[] {
  const out: PickView[] = []
  let overall = 1
  for (let r = 1; r <= rounds; r += 1) {
    for (let i = 0; i < nManagers; i += 1) {
      const idx = r % 2 === 1 ? i : nManagers - 1 - i
      const mid = `m${String(idx + 1).padStart(2, '0')}`
      out.push({ overall, round: r, pick_in_round: i + 1, manager_id: mid, original_manager_id: mid, keeper_player_id: null })
      overall += 1
    }
  }
  return out
}

export function makeState(overrides: Partial<DraftStateView> = {}): DraftStateView {
  const league = defaultLeague(12, 6)
  const schedule = makeSchedule()
  const rosters: Record<string, string[]> = {}
  for (const m of league.managers) rosters[m.id] = []
  return {
    draft_revision: 0,
    strategy_revision: 0,
    league_revision: 0,
    last_seq: 1,
    is_complete: false,
    format_confirmed: false,
    current_pick: schedule[0],
    on_clock_manager_id: 'm01',
    user_next_pick: schedule[5],
    user_following_pick: schedule[18],
    picks_until_user_turn: 5,
    picks: [],
    schedule,
    rosters,
    drafted_player_ids: [],
    current_rosters: { ...rosters },
    owned_player_ids: [],
    has_roster_moves: false,
    remaining_user_picks: 13,
    warnings: [],
    strategy: { mode: 'balanced', punts: {}, weights: {}, soft_punt_weight: 0.35, risk: 'neutral', suggest_punts: false, sim_budget_ms: 4000, sim_scenarios: 400, projection_blend_espn_weight: 0.5, roster_aware: false, roster_scale: 3.6 },
    league,
    ...overrides,
  }
}

export function makeIds(state: DraftStateView, extra: Partial<ResponseIds> = {}): ResponseIds {
  return {
    draft_revision: state.draft_revision,
    strategy_revision: state.strategy_revision,
    league_revision: state.league_revision,
    last_seq: state.last_seq,
    snapshot_id: 'demo-test',
    projection_version: 'proj-v1',
    seed: 1,
    ...extra,
  }
}

export function makeCandidate(id: string, name = id): CandidateView {
  return {
    player_id: id,
    name,
    team: 'DM1',
    primary_position: 'PG',
    eligible_positions: ['PG'],
    eligibility_verified: true,
    injury_status: 'ACTIVE',
    score: 1,
    tier: 1,
    base_value: 2,
    replacement_value: 1,
    replacement_player_id: null,
    replacement_name: null,
    slot: 'PG',
    fills_open_starting_slot: true,
    completion_ok: true,
    risk_adjustment: 0,
    value_sd: 0.5,
    survival_hint: 'likely available',
    adp: 10,
    rank: 10,
    flags: [],
    z: {},
    contributions: {},
    reasons: [],
    per_game: {},
    games: 70,
    minutes: 30,
    projection_source: 'demo',
    category_deltas: null,
  }
}

export function makeRec(state: DraftStateView, ids: string[]): RecommendationResponse {
  const shortlist = ids.map((id) => makeCandidate(id))
  return {
    ids: makeIds(state),
    tier: 'A',
    computed_ms: 5,
    highlighted: shortlist[0] ?? null,
    shortlist,
    user_roster: {
      assignments: [],
      unassigned: [],
      open_starting_slots: [],
      bench_used: 0,
      legal: true,
      caps_ok: true,
      cap_violations: {},
      completion_feasible: true,
      completion_detail: '',
      coverage_ratio: 1,
    },
    category_profile: { totals: {}, attempts: {}, z: {}, punt_labels: {}, weights: {}, unit: 'season totals', standardization: {} },
    notes: [],
    preview_player_id: null,
  }
}
