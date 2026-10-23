"""Typed request/response contracts (the OpenAPI spec drives the frontend's generated types)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.draft.events import EventType
from app.league.config import CategoryDef, LeagueConfig
from app.league.strategy import Strategy


class ResponseIds(BaseModel):
    draft_revision: int
    strategy_revision: int
    league_revision: int
    last_seq: int
    snapshot_id: str
    projection_version: str
    seed: int


class SessionCreate(BaseModel):
    league: LeagueConfig
    strategy: Strategy | None = None
    snapshot_id: str | None = None
    name: str | None = None


class SessionSummary(BaseModel):
    id: str
    name: str
    snapshot_id: str | None
    created_at: str
    updated_at: str
    last_seq: int | None = None
    n_commits: int | None = None


class PickView(BaseModel):
    overall: int
    round: int
    pick_in_round: int
    manager_id: str
    original_manager_id: str
    keeper_player_id: str | None = None


class PickRecordView(BaseModel):
    overall: int
    manager_id: str
    player_id: str
    is_keeper: bool
    source: str
    seq: int


class DraftStateView(BaseModel):
    draft_revision: int
    strategy_revision: int
    league_revision: int
    last_seq: int
    is_complete: bool
    format_confirmed: bool
    current_pick: PickView | None
    on_clock_manager_id: str | None
    user_next_pick: PickView | None
    user_following_pick: PickView | None
    picks_until_user_turn: int | None
    picks: list[PickRecordView]
    schedule: list[PickView]
    rosters: dict[str, list[str]]
    drafted_player_ids: list[str]
    current_rosters: dict[str, list[str]]  # draft picks ± post-draft moves (adds, drops, trades)
    owned_player_ids: list[str]
    has_roster_moves: bool
    remaining_user_picks: int
    warnings: list[str]
    strategy: Strategy
    league: LeagueConfig


class SessionDetail(BaseModel):
    meta: SessionSummary
    state: DraftStateView


class EventRequest(BaseModel):
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    expected_revision: int | None = None
    source: str = "manual"


class EventView(BaseModel):
    seq: int
    type: EventType
    payload: dict[str, Any]
    idempotency_key: str
    created_at: str
    source: str


class EventResponse(BaseModel):
    event: EventView
    state: DraftStateView
    deduplicated: bool


class BatchItem(BaseModel):
    type: EventType
    payload: dict[str, Any]
    idempotency_key: str | None = None


class BatchRequest(BaseModel):
    items: list[BatchItem]
    expected_revision: int | None = None
    source: str = "import"


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class SnapshotMeta(BaseModel):
    snapshot_id: str
    label: str
    source: str
    season: str
    created_at: str
    n_players: int
    is_demo: bool
    adp_platform: str | None
    adp_asof: str | None
    rank_source: str | None
    health: dict[str, Any]
    provenance: dict[str, Any]


class PlayerView(BaseModel):
    player_id: str
    name: str
    team: str | None
    espn_id: int | None = None  # for ESPN headshots and links
    primary_position: str | None
    eligible_positions: list[str]
    eligibility_source: str
    eligibility_verified: bool
    injury_status: str | None
    age: float | None
    is_rookie: bool
    adp: float | None
    rank: float | None
    projection_source: str
    per_game: dict[str, float]
    per_game_sd: dict[str, float]
    drafted_by: str | None = None
    drafted_overall: int | None = None


class CategoryDelta(BaseModel):
    before: float | None
    after: float | None
    delta: float | None
    unit: str


class CandidateView(BaseModel):
    player_id: str
    name: str
    team: str | None
    primary_position: str | None
    eligible_positions: list[str]
    eligibility_verified: bool
    injury_status: str | None
    score: float
    tier: int
    base_value: float
    replacement_value: float
    replacement_player_id: str | None
    replacement_name: str | None
    slot: str | None
    fills_open_starting_slot: bool
    completion_ok: bool
    risk_adjustment: float
    value_sd: float
    survival_hint: str
    adp: float | None
    rank: float | None
    flags: list[str]
    z: dict[str, float]
    contributions: dict[str, float]
    reasons: list[str]
    per_game: dict[str, float]
    games: float
    minutes: float
    projection_source: str
    category_deltas: dict[str, CategoryDelta] | None = None
    refined_score: float | None = None
    refined_detail: dict[str, Any] | None = None


class RosterSlotView(BaseModel):
    slot: str
    player_id: str | None
    name: str | None


class RosterView(BaseModel):
    assignments: list[RosterSlotView]
    unassigned: list[str]
    open_starting_slots: list[str]
    bench_used: int
    legal: bool
    caps_ok: bool
    cap_violations: dict[str, int]
    completion_feasible: bool
    completion_detail: str
    coverage_ratio: float


class CategoryProfile(BaseModel):
    totals: dict[str, float | None]
    attempts: dict[str, float]
    z: dict[str, float]
    punt_labels: dict[str, str | None]
    weights: dict[str, float]  # effective weights = strategy weight × marginal value
    marginal_value: dict[str, float] | None = None  # 1 = full value, lower when the roster is far ahead/behind
    unit: str = "projected season totals (per-game × projected games)"
    standardization: dict[str, Any]


class FastRecommendRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=200)
    preview_player_id: str | None = None  # evaluate as if the user had already drafted this player
    include_deltas: int = Field(default=8, ge=0, le=50)


class RecommendationResponse(BaseModel):
    ids: ResponseIds
    tier: str  # "A" | "B" | "C"
    computed_ms: float
    highlighted: CandidateView | None
    shortlist: list[CandidateView]
    user_roster: RosterView
    category_profile: CategoryProfile
    notes: list[str]
    preview_player_id: str | None = None
    preview_candidate: CandidateView | None = None  # the previewed player scored against the roster without them


class CompareRequest(BaseModel):
    player_ids: list[str] = Field(min_length=2, max_length=3)


class CompareResponse(BaseModel):
    ids: ResponseIds
    players: list[CandidateView]
    keys: list[str]


class RefineRequest(BaseModel):
    limit: int = Field(default=8, ge=2, le=20)
    budget_ms: int | None = None
    scenarios: int | None = None
    seed: int | None = None


class JobAccepted(BaseModel):
    job_id: str
    ids: ResponseIds
    status: str


class JobView(BaseModel):
    job_id: str
    status: str
    ids: dict[str, Any]
    stale: bool
    result: RefinementResponse | None = None
    error: str | None = None
    elapsed_ms: float | None = None


class ImportPreviewRequest(BaseModel):
    kind: Literal["projections", "eligibility", "adp", "picks"]
    text: str = Field(min_length=1, max_length=5_000_000)


class ImportRowView(BaseModel):
    row: int
    player_id: str | None
    matched_name: str | None
    errors: list[str]
    warnings: list[str]
    data: dict[str, Any]


class ImportPreviewView(BaseModel):
    kind: str
    columns: list[str]
    missing_columns: list[str]
    n_rows: int
    n_ok: int
    n_error: int
    notes: list[str]
    rows: list[ImportRowView]


class ImportApplyRequest(BaseModel):
    kind: Literal["projections", "eligibility", "adp", "picks"]
    text: str = Field(min_length=1, max_length=5_000_000)
    skip_error_rows: bool = False
    expected_revision: int | None = None


class ImportApplyResponse(BaseModel):
    kind: str
    applied_rows: int
    skipped_rows: int
    snapshot_id: str | None = None
    state: DraftStateView | None = None


class PuntScenario(BaseModel):
    key: str
    label: str
    punts: dict[str, str]
    objective: float
    se: float
    delta_vs_balanced: float
    category_win_probs: dict[str, float]
    strong_categories: int  # win probability >= 55%
    tossup_categories: int  # 45–55%
    likely_targets: list[str]  # most frequent next pick in the rollouts
    is_current: bool


class PuntAdvisorRequest(BaseModel):
    budget_ms: int = Field(default=6000, ge=500, le=60000)
    seed: int | None = None


class PuntAdvisorResponse(BaseModel):
    ids: ResponseIds
    objective_label: str
    computed_ms: float
    rollouts: int
    scenarios: list[PuntScenario]
    notes: list[str]


class HealthView(BaseModel):
    status: str
    data_dir: str
    snapshots: list[SnapshotMeta]
    default_snapshot_id: str
    snapshot_errors: dict[str, str]
    sessions: int
    data_health: dict[str, Any]


class RefinedCandidate(BaseModel):
    player_id: str
    name: str
    layer_a_score: float
    utility_now: float  # expected objective if drafted now (roster completed by the continuation policy)
    utility_alternative: float  # expected objective of the best alternative at this pick
    marginal_utility: float  # utility_now - utility_alternative
    survival_probability: float | None  # P(still available at the user's next pick); None when no demand model
    survival_label: str  # "model estimate" | "proxy" | "n/a"
    wait_value: (
        float | None
    )  # expected utility of waiting (taking the best alternative now, this player later if available)
    draft_now_advantage: float | None  # utility_now - wait_value
    objective_estimate: float  # format-specific: expected categories won / P(win matchup) / expected roto points
    objective_label: str
    category_win_probs: dict[str, float]
    uncertainty: float  # Monte Carlo standard error of marginal_utility
    tier: int
    explanation: list[str]


class RefinementResponse(BaseModel):
    ids: ResponseIds
    tier: str  # "B" or "C"
    computed_ms: float
    budget_ms: int
    scenarios: int
    seed: int
    objective_label: str
    opponent_model: str
    highlighted_player_id: str | None
    candidates: list[RefinedCandidate]
    notes: list[str]


JobView.model_rebuild()


class ManagerProfile(BaseModel):
    manager_id: str
    name: str
    is_user: bool
    n_players: int
    totals: dict[str, float | None]  # category -> projected season total or rate
    attempts: dict[str, float]  # FGA, FTA
    z: dict[str, float]  # sum of player total-z per category (strategy-unweighted)
    rank: dict[str, int | None]  # 1 = best in the league for that category
    categories_top3: int  # categories where this manager ranks in the top 3


class LeagueProfilesResponse(BaseModel):
    ids: ResponseIds
    keys: list[str]
    managers: list[ManagerProfile]
    unit: str = "projected season totals (per-game × projected games); rates are makes ÷ attempts"


# --- ESPN league link / sync ------------------------------------------------------------------


class LinkRequest(BaseModel):
    league_id: int = Field(gt=0)
    overrides: dict[str, int] = Field(default_factory=dict, description="manager id -> ESPN team id")


class EspnTeamView(BaseModel):
    team_id: int
    name: str
    owner_name: str
    n_players: int


class TeamMatchView(BaseModel):
    manager_id: str
    manager_name: str
    team_id: int
    team_name: str
    owner_name: str
    overlap: float
    confidence: str


class LinkPreview(BaseModel):
    league_id: int
    league_name: str
    teams: list[EspnTeamView]
    mapping: list[TeamMatchView]
    unmatched_managers: list[str]
    unmatched_teams: list[int]
    settings_warnings: list[str]
    warnings: list[str]


class LinkApplyRequest(BaseModel):
    league_id: int = Field(gt=0)
    mapping: dict[str, int]


class SyncRequest(BaseModel):
    expected_revision: int | None = None


class RosterDiffView(BaseModel):
    manager_id: str
    team_id: int
    added: list[str]
    dropped: list[str]
    source_refs: list[str]


class UnknownPlayerView(BaseModel):
    espn_id: int
    name: str


class SyncResult(BaseModel):
    ids: ResponseIds
    fetched_at: str
    summary: str
    changes: list[RosterDiffView]
    warnings: list[str]
    unknown_players: list[UnknownPlayerView]
    state: DraftStateView


# --- season reads --------------------------------------------------------------------------------


class TeamPowerView(BaseModel):
    manager_id: str
    name: str
    is_user: bool
    expected_cats: float
    rank: int
    cat_win_prob: dict[str, float]
    z: dict[str, float]
    n_players: int
    n_ir: int


class MatchupOddsView(BaseModel):
    period: int
    manager_a: str
    manager_b: str
    expected_a: float
    expected_b: float
    p_win_a: float
    p_tie: float
    p_win_b: float
    cat_p_a: dict[str, float]
    modal_score: list[float]
    games_a: int
    games_b: int
    notes: list[str]


class MatchupPairView(BaseModel):
    period: int
    home_manager_id: str
    away_manager_id: str | None  # None = bye
    odds: MatchupOddsView | None


class MatchupResponse(BaseModel):
    ids: ResponseIds
    odds: MatchupOddsView


class SeasonOverview(BaseModel):
    ids: ResponseIds
    linked: bool
    league_name: str | None
    synced_at: str | None
    summary: str | None
    warnings: list[str]
    current_period: int
    league_categories: list[CategoryDef]
    manager_names: dict[str, str]
    power: list[TeamPowerView]
    movement: dict[str, int]  # previous rank - current rank (positive = climbed)
    matchups: list[MatchupPairView]
    user_matchup: MatchupPairView | None


class FreeAgentView(BaseModel):
    player: PlayerView
    score: float
    z: dict[str, float]
    best_drop: PlayerView | None
    drop_value: float
    swap_delta: float
    injury_status: str | None
    percent_owned: float | None
    flags: list[str]


class FreeAgentsResponse(BaseModel):
    ids: ResponseIds
    items: list[FreeAgentView]
    synced_at: str | None


class WeekSideView(BaseModel):
    manager_id: str
    values: dict[str, float | None]
    results: dict[str, str | None]
    cats_won: float


class WeekResultView(BaseModel):
    period: int
    home: WeekSideView
    away: WeekSideView | None
    winner: str


class WeekResultsResponse(BaseModel):
    ids: ResponseIds
    period: int
    results: list[WeekResultView]
    projected: list[MatchupPairView]


class PredictionView(BaseModel):
    period: int
    home_manager_id: str
    away_manager_id: str | None
    predicted_winner: str | None  # None on a bye
    p_winner: float | None
    p_tie: float | None
    expected_home: float | None
    expected_away: float | None
    locked: bool  # frozen: the week had started when last written
    predicted_at: str
    actual_winner: str | None  # manager id, "tie", or None while undecided
    actual_cats: dict[str, float] | None
    correct: bool | None


class PredictionSummary(BaseModel):
    n_predicted: int
    n_decided: int
    n_correct: int
    hit_rate: float | None
    brier: float | None  # mean (p_winner - outcome)^2 over decided weeks; lower is better
    by_period: dict[str, dict[str, int]]


class PredictionsResponse(BaseModel):
    ids: ResponseIds
    predictions: list[PredictionView]
    summary: PredictionSummary


class PerformerRow(BaseModel):
    rank: int
    player: PlayerView
    games: int
    periods: int
    minutes: float
    contribution: float  # cumulative category value on the projection z scale (value-games)
    contribution_per_game: float | None
    expected_contribution: float | None  # projection per game x games played; None without a baseline
    over_expected: float | None
    over_expected_per_game: float | None
    actual: dict[str, float | None]  # totals (counting, makes/attempts) + FG_PCT/FT_PCT
    expected: dict[str, float | None] | None
    actual_per_game: dict[str, float | None]
    expected_per_game: dict[str, float | None] | None
    category_z: dict[str, float]  # per-category actual z (per game) minus projected z (per game)
    contribution_by_category: dict[str, float]  # cumulative units per category (sums to contribution)
    expected_by_category: (
        dict[str, float] | None
    )  # cumulative expected units per category (sums to expected_contribution)
    flags: list[str]


class PerformersResponse(BaseModel):
    ids: ResponseIds
    manager_id: str
    scope: Literal["week", "season"]
    period: int | None
    periods_available: list[int]
    baseline: str
    source: str
    categories: list[CategoryDef]
    unit_sizes: dict[str, float]  # per-game amount of each category worth one contribution unit
    benchmark_rates: dict[str, float]  # pool FG% / FT% that shooting impact is measured against
    contributors: list[PerformerRow]
    overperformers: list[PerformerRow]
    notes: list[str]
