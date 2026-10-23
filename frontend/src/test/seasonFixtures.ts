import type { FreeAgentView, PlayerView, SeasonOverview } from '../api/types'

export function makePlayer(id: string, name: string, team = 'BOS'): PlayerView {
  return {
    player_id: id,
    name,
    team,
    primary_position: 'PG',
    eligible_positions: ['PG', 'G'],
    eligibility_verified: true,
    injury_status: null,
    adp: null,
    rank: null,
    projection_source: 'demo',
    per_game: {},
    per_game_sd: {},
    drafted_by: null,
    drafted_overall: null,
  } as PlayerView
}

export function makeFreeAgent(id: string, name: string, flags: string[] = []): FreeAgentView {
  return { player: makePlayer(id, name), score: 1.5, z: { PTS: 0.4 }, best_drop: makePlayer('d1', 'Bench Guy'), drop_value: 0.2, swap_delta: 1.3, injury_status: flags.includes('out') ? 'OUT' : 'ACTIVE', percent_owned: 12.5, flags }
}

export function makeOverview(over: Partial<SeasonOverview> = {}): SeasonOverview {
  return {
    ids: { draft_revision: 1, strategy_revision: 0, league_revision: 1, last_seq: 1, snapshot_id: 'x', projection_version: 'v', seed: 1 },
    linked: true,
    league_name: 'L',
    synced_at: null,
    summary: null,
    warnings: [],
    current_period: 1,
    league_categories: [{ key: 'PTS', label: 'Points', higher_is_better: true, kind: 'counting', numerator: null, denominator: null }],
    manager_names: {},
    power: [],
    movement: {},
    matchups: [],
    user_matchup: null,
    ...over,
  }
}
