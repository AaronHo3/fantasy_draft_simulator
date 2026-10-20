# ESPN League Link and Season Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link a completed draft session to a public ESPN league so rosters, weekly matchups, power rankings, free agents and actual results stay current from ESPN without hand-typed teams.

**Architecture:** A pure parser over the ESPN league JSON feeds a sync planner that diffs ESPN rosters against the event-replayed session rosters and appends one `roster_changed` event per sync. Season analytics (`season/power.py`) reuse the existing weekly simulation with common random numbers; a new Season screen in the frontend reads four read-only endpoints and one sync action.

**Tech Stack:** Python 3.12, FastAPI, pydantic, NumPy/pandas, httpx, SQLite (sessions), pytest; React 19 + TypeScript + zustand + vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-19-espn-league-link-design.md`

## Global Constraints

- Read-only: no request method other than GET to ESPN, ever.
- No cookies in this iteration. 401/403 from ESPN → `LeagueAccessError`; API maps to 409 `league_private`.
- Rosters and ownership derive from the event log (`roster_changed` events), never from a mutable table. `session_sync` holds cache only.
- Every season response carries `ResponseIds` (`draft_revision`, `strategy_revision`, `snapshot_id`, `projection_version`, `seed`).
- FG%/FT% from summed makes/attempts; categories come from the session's `LeagueConfig` (8 here, no TOV).
- No network call inside `season/power.py`, `engine/*`, or any `GET /season/*` handler.
- ESPN seasonId = 2027 for NBA 2026-27 (`espn_season_id(league.season)`); player identity through snapshot `Player.espn_id`.
- Pure functions return new values; no input mutation. Files ≤ 800 lines, functions ≤ 50 lines where practical.
- Use `ruff` formatting; run `make test` before each commit touching backend + frontend.

## Review Focus

1. A player on ESPN that is in no snapshot (callup/two-way) — must be owned (not a free agent) and not crash analytics. Test in Task 4 (`test_plan_sync_unknown_player_is_owned_placeholder`) and Task 6 (`test_power_ignores_unknown_player`).
2. The 13-team bye week: a matchup with `away=None` must appear as a bye, not an error, and the user's "next opponent" must be "bye" that week. Test in Task 1 (`test_parse_matchups_bye`) and Task 7 (`test_overview_user_bye`).
3. Two syncs racing (auto-refresh + manual): the second must not double-apply. Test in Task 5 (`test_sync_conflict_on_stale_revision`).
4. ESPN has 14 players on a team (IR used): roster size validation must allow starting+bench+IR and IR player must not count as a starter. Test in Task 3 (`test_roster_changed_allows_ir_size`) and Task 6 (`test_power_excludes_ir_from_starters`).
5. Schedule parquet missing (fresh clone, no `make refresh`): matchup odds fall back to season averages with a note instead of a 500. Test in Task 6 (`test_matchup_odds_without_schedule_falls_back`).

---

### Task 1: ESPN league parser

**Files:**
- Create: `backend/app/sources/espn_league.py`
- Create: `backend/tests/fixtures/espn_league_small.json` (trim of the real payload: teams 1, 7, 9 with full rosters; `members` for those owners; schedule entries for periods 1 and 2 including the period-1 bye entry `id=1` (home 8, away None) rewritten to home team 1; transactions: the 6 George adds/drops with ids kept, 1 LINEUP, 1 DRAFT; `settings` untrimmed; `status` untrimmed). Build it with a script from `/private/tmp/claude-501/-Users-aaronho-Projects-Code-fantasy-espn-9cat-simulator/ec586260-5b7a-4169-a36c-86eb835cec88/scratchpad/espn/league.json`; keep under 300 KB.
- Test: `backend/tests/sources/test_espn_league.py`

**Interfaces:**
- Consumes: `app.sources.base.RawResponse, SchemaError, with_retries`; `app.sources.espn_public._get, USER_AGENT`; `app.sources.espn_private.STAT_ID_TO_CATEGORY, _slot_counts_to_lists` (import; do not duplicate).
- Produces (all frozen dataclasses in `espn_league.py`):
  - `EspnSettings(name: str, scoring_type: str, stat_ids: tuple[int, ...], lineup_slot_counts: dict[int, int], position_limits: dict[int, int], lineup_lock_type: str, matchup_period_count: int, playoff_team_count: int, current_matchup_period: int, scoring_period_id: int)`
  - `EspnRosterEntry(espn_player_id: int, name: str, lineup_slot_id: int, injury_status: str, acquisition_type: str, pro_team_id: int | None)`
  - `EspnTeam(team_id: int, abbrev: str, name: str, owner_ids: tuple[str, ...], owner_name: str, roster: tuple[EspnRosterEntry, ...], wins: int, losses: int, ties: int, playoff_seed: int | None, waiver_rank: int | None)`
  - `EspnStatLine(score: float, result: str | None)`; `EspnMatchupSide(team_id: int, by_stat: dict[int, EspnStatLine])`
  - `EspnMatchup(matchup_id: int, period: int, home: EspnMatchupSide, away: EspnMatchupSide | None, winner: str)`
  - `EspnTransactionItem(kind: str, espn_player_id: int, from_team_id: int, to_team_id: int)`; `EspnTransaction(transaction_id: str, kind: str, status: str, team_id: int, proposed_at: str, scoring_period_id: int, items: tuple[EspnTransactionItem, ...])` with property `is_roster_move -> bool` (True when status == "EXECUTED" and any item kind in {"ADD","DROP","TRADE"}).
  - `EspnLeague(league_id: int, season_id: int, settings: EspnSettings, teams: tuple[EspnTeam, ...], matchups: tuple[EspnMatchup, ...], transactions: tuple[EspnTransaction, ...], fetched_at: str)` with `team(team_id) -> EspnTeam`, `matchups_for(period) -> tuple[EspnMatchup, ...]`.
  - `class LeagueAccessError(RuntimeError)`
  - `LEAGUE_VIEWS = ("mTeam", "mRoster", "mSettings", "mMatchup", "mSchedule", "mTransactions2", "mStatus")`
  - `league_url(league_id: int, season_id: int) -> str` → `https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season_id}/segments/0/leagues/{league_id}`
  - `parse_league(payload: dict, league_id: int, season_id: int, fetched_at: str) -> EspnLeague`
  - `fetch_league_raw(league_id: int, season_id: int, client: httpx.Client | None = None) -> RawResponse` (raises `LeagueAccessError` on 401/403, `SchemaError` on non-dict/no `teams`)
  - `fetch_league(league_id, season_id, client=None) -> EspnLeague`
  - `settings_diff(s: EspnSettings, league: LeagueConfig) -> list[str]` — lines for: scoring type ≠ format; category set ≠ (via `STAT_ID_TO_CATEGORY`); starting slots ≠ (`_slot_counts_to_lists`); bench/IR count ≠; C cap ≠ (`position_limits[5]`); `lineup_lock_type == "INDIVIDUAL_GAME"` while `league.lineup_mode == weekly` → "ESPN locks lineups per game (daily); the session is set to weekly".

- [ ] **Step 1: Build the fixture** with a throwaway script (scratchpad), assert file < 300 KB.
- [ ] **Step 2: Write failing tests** in `tests/sources/test_espn_league.py`:
  - `test_parse_settings`: name == "1000Thieves", scoring_type == "H2H_CATEGORY", stat_ids == (0,1,2,3,6,17,19,20), lineup_slot_counts[11] == 3, position_limits[5] == 4, lineup_lock_type == "INDIVIDUAL_GAME", matchup_period_count == 19, current_matchup_period == 1.
  - `test_parse_teams_and_rosters`: 3 teams; team 7 has 14 entries, exactly one with `lineup_slot_id == 13`; owner_name of team 7 == "George Hu"; entry names include "Cade Cunningham".
  - `test_parse_matchups_bye`: `matchups_for(1)` contains one with `away is None`; every other has both sides; `by_stat[0].result in {"WIN","LOSS","TIE",None}`.
  - `test_parse_transactions_roster_moves`: count of `is_roster_move` == 6 (George's 3 EXECUTED adds + 3 drops), CANCELED/FAILED ones False, LINEUP False.
  - `test_fetch_private_league_raises`: `httpx.MockTransport` returning 401 → `LeagueAccessError`.
  - `test_settings_diff_flags_daily_vs_weekly`: with the session-like `LeagueConfig` (8 cats, weekly) → one line containing "daily"; with lineup_mode daily and matching cats → `[]`.
- [ ] **Step 3: Run** `cd backend && uv run pytest tests/sources/test_espn_league.py -v` → FAIL (import error).
- [ ] **Step 4: Implement** `espn_league.py` per Interfaces. Owner name = `f"{firstName} {lastName}".strip()` from `members` by `primaryOwner`, fallback team name. `proposed_at` = ISO UTC from epoch ms.
- [ ] **Step 5: Run tests** → PASS. `uv run ruff check app tests`.
- [ ] **Step 6: Commit** `feat: parse public ESPN league payload (settings, rosters, matchups, transactions)`.

### Task 2: League config link fields and schedule week windows

**Files:**
- Modify: `backend/app/league/config.py` (LeagueConfig)
- Create: `backend/app/season/weeks.py`
- Test: `backend/tests/test_league_config.py` (append), `backend/tests/test_weeks.py`

**Interfaces:**
- Produces on `LeagueConfig`: `espn_league_id: int | None = None`, `espn_team_ids: dict[str, int] = {}` (manager_id → ESPN team id; validator: keys ⊆ manager ids, values unique), `espn_linked_at: str | None = None`.
- Produces in `season/weeks.py`:
  - `SEASON_START = date(2026, 10, 20)` for season "2026-27"; `season_start(season: str) -> date` (lookup table `{"2026-27": date(2026,10,20)}`, else `ValueError`).
  - `period_window(season: str, period: int) -> tuple[date, date]`: period 1 = (season_start, following Sunday inclusive); period k = Monday-anchored week k; so period 1 = (2026-10-20, 2026-10-26), period 2 = (2026-10-27, 2026-11-02).
  - `games_in_window(schedule: pd.DataFrame, start: date, end: date) -> dict[str, int]` team tricode → games with `date_utc` shifted by `schedule_model.US_SHIFT_HOURS` falling in [start, end].
  - `current_period(season: str, today: date) -> int` (clamped 1..22).

- [ ] **Step 1: Write failing tests**: `test_league_config_espn_fields_validate` (duplicate team id → ValueError; unknown manager key → ValueError; round-trips through `model_dump_json`); `test_period_window_week1_and_2` with values above; `test_games_in_window_counts_us_dates` using a 4-row frame where one game at `2026-10-27T01:30:00+00:00` (US evening Oct 26) counts in period 1; `test_current_period`: 2026-10-19 → 1, 2026-10-28 → 2.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/test_league_config.py tests/test_weeks.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: ESPN link fields on LeagueConfig and matchup period windows`.

### Task 3: `roster_changed` event and current rosters

**Files:**
- Modify: `backend/app/draft/events.py` (EventType, DraftState, apply)
- Modify: `backend/app/recommend/service.py:68-92` (`user_context`), `service.py:373-409` (`state_view`)
- Modify: `backend/app/api/schemas.py` (`DraftStateView`)
- Test: `backend/tests/test_events_store.py` (append)

**Interfaces:**
- `EventType.roster_changed = "roster_changed"` (not in `DRAFT_EVENTS`).
- `@dataclass(frozen=True) class RosterMove: manager_id: str; added: tuple[str, ...]; dropped: tuple[str, ...]; source_ref: str; seq: int`
- `DraftState.moves: tuple[RosterMove, ...] = ()`; `DraftState.owned_player_ids -> frozenset[str]`; `DraftState.current_roster(manager_id) -> tuple[str, ...]`; `DraftState.current_rosters() -> dict[str, tuple[str, ...]]`; `DraftState.has_roster_moves -> bool`.
- `apply` for `roster_changed`: requires `state.is_complete` else `DraftError("draft_incomplete")`; validates per spec (drops first, then adds; `roster_conflict`); bumps `draft_revision`. `pick_undone`/`pick_corrected` raise `DraftError("draft_locked")` when `has_roster_moves`.
- `user_context`: `roster = state.current_roster(uid)` and `drafted = state.owned_player_ids` when `state.is_complete`, unchanged otherwise.
- `DraftStateView` gains `current_rosters: dict[str, list[str]]`, `owned_player_ids: list[str]`, `has_roster_moves: bool`.

- [ ] **Step 1: Write failing tests**: `test_roster_changed_requires_complete_draft`; `test_roster_changed_trade_is_atomic` (two managers swap in one event → both `current_roster` updated); `test_roster_changed_rejects_add_of_owned_player` (`roster_conflict`); `test_roster_changed_rejects_drop_by_non_owner`; `test_roster_changed_allows_ir_size` (roster of 14 accepted); `test_undo_locked_after_roster_change` (`draft_locked`); `test_state_view_exposes_current_rosters`. Use `demo_league_config(n_managers=2)` and a helper that commits every pick of a small league to reach `is_complete`.
- [ ] **Step 2: Run** `uv run pytest tests/test_events_store.py -v` → FAIL.
- [ ] **Step 3: Implement** in `events.py`; thread through `service.py` and `schemas.py`.
- [ ] **Step 4: Run** full backend tests → PASS. Run `make openapi` (regenerates `frontend/src/api/schema.d.ts`), `make typecheck` → PASS.
- [ ] **Step 5: Commit** `feat: roster_changed events and post-draft current rosters`.

### Task 4: Team mapping and sync planning (pure)

**Files:**
- Create: `backend/app/season/link.py`
- Create: `backend/app/season/sync.py`
- Test: `backend/tests/test_season_link_sync.py`

**Interfaces:**
- `link.py`:
  - `@dataclass(frozen=True) class TeamMatch: manager_id: str; team_id: int; overlap: float; name_similarity: float; confidence: str  # "high" (overlap ≥ 0.6) | "medium" (≥ 0.3) | "low"`
  - `@dataclass(frozen=True) class TeamMapping: matches: tuple[TeamMatch, ...]; unmatched_managers: tuple[str, ...]; unmatched_teams: tuple[int, ...]; warnings: tuple[str, ...]`; `as_dict() -> dict[str, int]`.
  - `match_teams(state: DraftState, league: EspnLeague, snap: Snapshot, overrides: dict[str, int] | None = None) -> TeamMapping`. Overlap = |drafted ids of manager ∩ ESPN roster ids (mapped via `espn_id`)| / |drafted ids|. Assignment: greedy by descending (overlap, name_similarity) with `difflib.SequenceMatcher` on normalized names; overrides fixed first.
- `sync.py`:
  - `@dataclass(frozen=True) class RosterDiff: manager_id: str; team_id: int; added: tuple[str, ...]; dropped: tuple[str, ...]; source_refs: tuple[str, ...]`
  - `@dataclass(frozen=True) class SyncPlan: fetched_at: str; diffs: tuple[RosterDiff, ...]; events: tuple[tuple[EventType, dict, str], ...]; warnings: tuple[str, ...]; unknown_players: tuple[tuple[int, str], ...]; summary: str`
  - `canonical_id(snap: Snapshot, espn_player_id: int, name: str) -> str` → snapshot player_id by `espn_id`, else `f"espn:{espn_player_id}"`.
  - `plan_sync(state: DraftState, league: EspnLeague, snap: Snapshot, mapping: dict[str, int]) -> SyncPlan`. Zero diffs → `events == ()`. Otherwise one `roster_changed` event with idempotency key `f"espn-sync:{league.league_id}:{league.fetched_at}"`, `effective_at = fetched_at`, `note = summary`. Attribution: an add/drop whose (player, team) matches an executed transaction item gets `espn:<transaction_id>`, else `espn:roster-diff`. Also a `league_updated` event first when `state.league.espn_team_ids != mapping` or `espn_league_id` differs (payload `{"league": updated_config}`), key `f"espn-link:{league.league_id}:{fetched_at}"`.
  - `summary` format: `"ESPN sync: {n_adds} adds, {n_drops} drops across {n_teams} teams; {n_unknown} unknown players"`.

- [ ] **Step 1: Write failing tests** using the fixture league, a demo snapshot patched so three fixture players have matching `espn_id`s (build a tiny `Snapshot` via the existing demo builder and `dataclasses.replace` the players): `test_match_teams_by_overlap_with_renamed_owner`; `test_match_teams_override_wins`; `test_plan_sync_no_changes_has_no_events`; `test_plan_sync_adds_drops_attributed_to_transactions`; `test_plan_sync_trade_in_one_event`; `test_plan_sync_unknown_player_is_owned_placeholder` (unknown ESPN id → id `espn:<id>`, listed in `unknown_players`, present in `added`); `test_plan_sync_first_sync_writes_league_updated`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/test_season_link_sync.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: ESPN team mapping by roster overlap and pure sync planner`.

### Task 5: Sync persistence, live status, API link/sync

**Files:**
- Modify: `backend/app/persistence/store.py` (new table `session_sync`)
- Create: `backend/app/season/live_status.py`
- Modify: `backend/app/api/deps.py` (schedule + live-status loaders), `backend/app/api/routes.py`, `backend/app/api/schemas.py`
- Modify: `backend/app/settings.py` (`live_dir` property → `data_dir/"nba"/"live"`)
- Test: `backend/tests/test_api_season.py` (new), `backend/tests/test_events_store.py` (append)

**Interfaces:**
- `SessionStore.set_sync(session_id, record: dict) -> None` / `get_sync(session_id) -> dict | None`; table `session_sync(session_id TEXT PRIMARY KEY, league_id INTEGER, fetched_at TEXT, summary TEXT, record_json TEXT)`; created in the existing schema init (idempotent `CREATE TABLE IF NOT EXISTS`). `record` keys: `league_id, fetched_at, summary, warnings, changes (list of RosterDiff dicts), power (list of {manager_id, expected_cats, rank}) | None, current_period`.
- `live_status.py`: `LIVE_COLUMNS = ("espn_id","injury_status","percent_owned","team","fetched_at")`; `write_live_status(live_dir: Path, league_id: int, players: pd.DataFrame) -> Path` (from `espn_public.parse_players` frame, select columns, atomic write to `live_dir/<league_id>/players.parquet`); `read_live_status(live_dir, league_id) -> pd.DataFrame | None`; `status_overlay(snap: Snapshot, live: pd.DataFrame | None) -> dict[str, dict]` player_id → `{injury_status, percent_owned, fetched_at}` (snapshot status when live missing).
- `AppContext` gains `schedule: pd.DataFrame | None` (lazy, `settings.data_dir/"nba"/"normalized"/"schedule.parquet"`) via `get_schedule()`, and `live_status(league_id) -> pd.DataFrame | None` (cached per league id, invalidated by sync).
- Schemas: `LinkRequest(league_id: int = Field(gt=0), overrides: dict[str, int] = {})`; `TeamMatchView`; `LinkPreview(league_name, teams: list[{team_id, name, owner_name, n_players}], mapping: list[TeamMatchView], unmatched_managers, unmatched_teams, settings_warnings: list[str])`; `LinkApplyRequest(league_id, mapping: dict[str, int])`; `SyncRequest(expected_revision: int | None = None)`; `RosterDiffView`; `SyncResult(fetched_at, summary, changes: list[RosterDiffView], warnings: list[str], unknown_players: list[{espn_id, name}], state: DraftStateView, ids: ResponseIds)`.
- Routes:
  - `POST /sessions/{id}/espn/link` → `LinkPreview` (fetches league; no events).
  - `POST /sessions/{id}/espn/link/apply` → `SessionDetail` (appends `league_updated` with the three fields; `espn_linked_at = now`).
  - `POST /sessions/{id}/espn/sync` → `SyncResult`: requires `league.espn_league_id` else 409 `not_linked`; fetch league + players feed (players failure → warning); `plan_sync`; `append_batch(..., expected_revision, source="espn")`; `ConflictError` → 409 `revision_conflict`; write live status; compute power via Task 6 (`power_rankings`) and `set_sync`. `LeagueAccessError` → 409 `league_private` with message "ESPN league {id} is private. In ESPN: League → Settings → Basic Settings → Make League Viewable to Public (or add cookies to backend/.env)."; `httpx.HTTPError`/`SchemaError` → 502 `espn_unavailable`.
  - Fetchers injected through `AppContext.espn_fetch_league: Callable[[int, int], EspnLeague]` and `espn_fetch_players: Callable[[int], pd.DataFrame]` so tests can monkeypatch.

- [ ] **Step 1: Write failing tests** (`tests/test_api_season.py`): fixture `linked_client` that creates a demo session of 3 managers × 3 rounds, commits every pick, patches the two fetchers to return the fixture `EspnLeague` (with ids rewritten so demo players map) and an empty players frame; `test_link_preview_maps_teams`; `test_link_apply_sets_fields`; `test_sync_applies_roster_changes_and_is_idempotent` (second sync → `changes == []`, `last_seq` unchanged, `get_sync` updated); `test_sync_conflict_on_stale_revision` (409 `revision_conflict`); `test_sync_private_league_409`; `test_sync_not_linked_409`. Store test: `test_session_sync_roundtrip`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat: ESPN link and sync endpoints with sync cache and live player status`.

### Task 6: Season analytics (power, matchup odds, free agents, results)

**Files:**
- Create: `backend/app/season/power.py`, `backend/app/season/free_agents.py`, `backend/app/season/results.py`
- Test: `backend/tests/test_season_power.py`

**Interfaces:**
- `power.py`:
  - `N_SCENARIOS = 600`
  - `@dataclass(frozen=True) class TeamSim: manager_id: str; roster_idx: tuple[int, ...]; counted_idx: tuple[int, ...]  # starters by projected minutes, IR excluded`
  - `build_team_sims(snap, state, ir_player_ids: frozenset[str]) -> tuple[TeamSim, ...]` (unknown `espn:` ids skipped).
  - `simulate_league_week(snap, league, teams, seed, games_per_player: np.ndarray | None = None, zero_games: frozenset[str] = frozenset()) -> dict[str, np.ndarray]` manager → `[S, P]` totals (one `simulate_players_week` call shared by all teams; `games_per_player` overrides `team_games_per_week`; players in `zero_games` get 0 games).
  - `@dataclass(frozen=True) class TeamPower: manager_id: str; name: str; is_user: bool; expected_cats: float; rank: int; cat_win_prob: dict[str, float]; z: dict[str, float]; n_players: int; n_ir: int`
  - `power_rankings(snap, state, seed, ir_player_ids=frozenset(), n_scenarios=N_SCENARIOS) -> tuple[TeamPower, ...]`
  - `@dataclass(frozen=True) class MatchupOdds: period: int; manager_a: str; manager_b: str; expected_a: float; expected_b: float; p_win_a: float; p_tie: float; p_win_b: float; cat_p_a: dict[str, float]; modal_score: tuple[float, float]; games_a: int; games_b: int; notes: tuple[str, ...]`
  - `matchup_odds(snap, state, a: str, b: str, period: int, seed, schedule: pd.DataFrame | None, status: dict[str, dict], ir_player_ids, n_scenarios=N_SCENARIOS) -> MatchupOdds`: games per player from `weeks.games_in_window` by `Player.team`; players with `status[pid]["injury_status"] == "OUT"` or in IR → 0 games; `schedule is None` → season averages and note "schedule not loaded; using season-average games per week".
- `free_agents.py`:
  - `@dataclass(frozen=True) class FreeAgent: player_id: str; score: float; z: dict[str, float]; best_drop: str | None; swap_delta: float; injury_status: str | None; percent_owned: float | None; flags: tuple[str, ...]`
  - `free_agents(snap, state, status: dict[str, dict], ir_player_ids, limit=50, position: str | None = None, q: str | None = None) -> tuple[FreeAgent, ...]`: candidates from `rank_layer_a(user_context(state, snap))` (available = unowned). `best_drop`: roster player (not IR) minimizing loss of weighted z (`LayerAResult.weights`); `swap_delta = cand weighted z − drop weighted z`. OUT/IR players flagged `"out"` and sorted after healthy ones.
- `results.py`:
  - `ESPN_STAT_TO_KEY = {0:"PTS",6:"REB",3:"AST",2:"STL",1:"BLK",17:"FG3M",19:"FG_PCT",20:"FT_PCT",11:"TOV"}`; makes/attempts ids 13/14/15/16 used to recompute FG%/FT% when present.
  - `@dataclass(frozen=True) class WeekSide: manager_id: str; values: dict[str, float | None]; results: dict[str, str | None]; cats_won: float`
  - `@dataclass(frozen=True) class WeekMatchupResult: period: int; home: WeekSide; away: WeekSide | None; winner: str`
  - `week_results(league: EspnLeague, period: int, team_to_manager: dict[int, str], categories) -> tuple[WeekMatchupResult, ...]`; `cats_won` = wins + 0.5·ties over the session's categories.

- [ ] **Step 1: Write failing tests** with the demo snapshot and a completed 3-manager session: `test_power_rankings_deterministic_and_ranked` (same seed → identical; ranks 1..3; `sum(cat_win_prob)/C ≈ expected_cats/C` within 0.05); `test_power_excludes_ir_from_starters`; `test_power_ignores_unknown_player`; `test_matchup_odds_symmetric` (`p_win_a + p_tie + p_win_b == 1 ± 1e-9`; swapping a/b swaps numbers); `test_matchup_odds_out_player_zero_games` (expected_a drops when the user's top player is OUT); `test_matchup_odds_without_schedule_falls_back` (note present); `test_free_agents_exclude_owned_and_pick_best_drop` (no owned ids; `best_drop` not the top-minutes starter when a bench player exists; OUT sorted last); `test_week_results_from_scorebystat` (fixture period 2 pair → `cats_won` matches WIN/TIE counts).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Keep each module < 300 lines.
- [ ] **Step 4: Run** `uv run pytest tests/test_season_power.py -v` → PASS; `uv run python -c` timing check: `power_rankings` on the real snapshot with 13 teams < 2 s (record in PROGRESS.md).
- [ ] **Step 5: Commit** `feat: season analytics (power rankings, matchup odds, free agents, ESPN week results)`.

### Task 7: Season read endpoints and CLI

**Files:**
- Modify: `backend/app/api/routes.py`, `backend/app/api/schemas.py`, `backend/app/cli.py`, `Makefile`
- Test: `backend/tests/test_api_season.py` (append)

**Interfaces:**
- Schemas: `TeamPowerView`, `MatchupOddsView`, `MatchupPairView(period, home_manager_id, away_manager_id | None, odds: MatchupOddsView | None)`, `SeasonOverview(ids, linked: bool, league_name, synced_at, summary, warnings, current_period, power: list[TeamPowerView], movement: dict[str, int], matchups: list[MatchupPairView], user_matchup: MatchupPairView | None)`, `FreeAgentView(player: PlayerView, score, z, best_drop: PlayerView | None, swap_delta, injury_status, percent_owned, flags)`, `FreeAgentsResponse(ids, items, synced_at)`, `WeekSideView`, `WeekResultView`, `WeekResultsResponse(ids, period, results: list[WeekResultView], projected: list[MatchupPairView])`.
- Routes (all GET, no network): `/sessions/{id}/season/overview?seed=`, `/sessions/{id}/season/matchup?period=&team_a=&team_b=&seed=`, `/sessions/{id}/season/free-agents?limit=&position=&q=`, `/sessions/{id}/season/results?period=`. `results` needs the last fetched `EspnLeague`: sync stores the raw payload at `live_dir/<league_id>/league.json`; the results handler parses it (`parse_league`) — no network. `movement` = previous rank − current rank from `get_sync().power`. Unlinked session → `linked=False`, power/matchups from drafted rosters, `matchups=[]`.
- CLI: `espn-link SESSION LEAGUE_ID [--map m10=7 ...] [--apply]`, `espn-sync SESSION`, `season SESSION` prints ESPN results when linked. Makefile: `link: ... espn-link $(SESSION) $(LEAGUE) --apply`, `sync: ... espn-sync $(SESSION)`.

- [ ] **Step 1: Write failing tests**: `test_overview_linked_has_matchups_and_user_matchup`; `test_overview_user_bye` (fixture period with the user's team on the bye → `user_matchup.away_manager_id is None`); `test_free_agents_endpoint_excludes_owned`; `test_results_endpoint_from_cached_payload`; `test_overview_unlinked_still_returns_power`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** routes, CLI, Makefile.
- [ ] **Step 4: Run** `make test-backend`, `make openapi`, `make typecheck` → PASS.
- [ ] **Step 5: Commit** `feat: season overview, matchup, free-agent and results endpoints; link/sync CLI`.

### Task 8: Frontend season store and API client

**Files:**
- Modify: `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/lib/router.ts` (`Route` adds `'season'`), `frontend/src/App.tsx` (nav "Season" when `isComplete`)
- Create: `frontend/src/store/seasonStore.ts`
- Test: `frontend/src/store/seasonStore.test.ts`

**Interfaces:**
- `ApiClient` adds: `espnLinkPreview(id, body: LinkRequest): Promise<LinkPreview>`, `espnLinkApply(id, body: LinkApplyRequest): Promise<SessionDetail>`, `espnSync(id, expectedRevision?: number | null): Promise<SyncResult>`, `seasonOverview(id, seed?): Promise<SeasonOverview>`, `seasonMatchup(id, period, teamA, teamB): Promise<MatchupOddsView>`, `seasonFreeAgents(id, opts: {limit?, position?, q?}): Promise<FreeAgentsResponse>`, `seasonResults(id, period): Promise<WeekResultsResponse>`. Types exported from `types.ts` via `components['schemas'][...]`.
- `seasonStore.ts`: `createSeasonStore(deps: {api, storage, now: () => number})`; state `{overview, overviewStatus, freeAgents, faStatus, results, resultsStatus, syncStatus: 'idle'|'syncing'|'error', syncError, lastSync: SyncResult | null, autoRefreshMin: 0|15|60, period: number | null}`; actions `loadOverview(sessionId)`, `sync(sessionId, expectedRevision)` (then reload overview and `draftStore.loadSession`), `loadFreeAgents(sessionId, opts)`, `loadResults(sessionId, period)`, `setAutoRefresh(min)` (persists key `copilot.season.autoRefresh`; timer via `setInterval`, cleared on 0), `setPeriod(p)`.

- [ ] **Step 1: Write failing tests**: `sync updates lastSync and reloads overview`; `auto-refresh calls sync on the interval and stops at 0` (vi.useFakeTimers); `sync error keeps previous overview and sets syncError`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/store/seasonStore.test.ts` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** vitest + `npx tsc --noEmit -p tsconfig.app.json` → PASS.
- [ ] **Step 5: Commit** `feat(frontend): season store, API client methods and route`.

### Task 9: Season screen UI

**Files:**
- Create: `frontend/src/screens/SeasonScreen.tsx`, `frontend/src/components/season/{SyncBar,LinkDialog,MatchupsTab,MatchupCard,PowerTab,FreeAgentsTab,ResultsTab}.tsx`
- Modify: `frontend/src/App.tsx` (route), `frontend/src/components/draft/HistoryDrawer.tsx` (render `roster_changed`), `frontend/src/components/draft/TeamsPanel.tsx` + `OpponentRosters.tsx` (use `state.current_rosters`), `frontend/src/styles/index.css` (season tokens/classes only; reuse existing panel/table/badge classes)
- Test: `frontend/src/components/season/MatchupCard.test.tsx`, `frontend/src/components/season/FreeAgentsTab.test.tsx`

**Interfaces:**
- `SeasonScreen` tabs: `matchups | power | free-agents | results` (hash `#/season?tab=`). Unlinked → `LinkDialog` inline with league id input (prefilled from `?league=`), preview table (manager, ESPN team, owner, confidence badge, override `<select>`), settings warnings, Apply.
- `SyncBar` copy: `Linked to {league_name} · synced {relative time} · [Sync now] · Auto-refresh [Off|15 min|60 min]`; last summary line; warnings as `Badge kind="warn"`.
- `MatchupCard(pair: MatchupPairView, names, categories, isUser)`: header "A vs B", three numbers (win/tie/loss %), expected cats, per-category bar grid with the favored side highlighted; bye → "Bye week". User's card first with `data-testid="user-matchup"`.
- `PowerTab`: table rank, team, expected cats/week, Δ (▲/▼ from `movement`), per-category win-chance cells colored by the existing profile palette.
- `FreeAgentsTab`: search box, position select, "hide OUT" toggle; columns player, team/pos, status, % owned, value, best drop, net Δ, category deltas; row click → `PlayerDrawer`.
- `ResultsTab`: period select; per pairing a two-row table of actual category values with WIN/LOSS/TIE coloring and the projected `p_win_a` beneath.

- [ ] **Step 1: Write failing component tests**: `MatchupCard renders bye`, `MatchupCard highlights favored categories` (≥ 0.5 gets class `fav-a`), `FreeAgentsTab hides OUT when toggled`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** components and wire the screen; add nav entry; update HistoryDrawer/TeamsPanel/OpponentRosters.
- [ ] **Step 4: Run** `make test-frontend`, `make typecheck` → PASS. Manual check with `make dev BACKEND_PORT=8020 FRONTEND_PORT=5180` on session 5291db641583: link to 2075231076, sync, confirm George shows Ayton/Poole/Braun.
- [ ] **Step 5: Commit** `feat(frontend): Season screen with matchups, power rankings, free agents and results`.

### Task 10: End-to-end test, docs, decisions

**Files:**
- Create: `frontend/e2e/season.spec.ts` (Playwright `page.route` mocks `/api/sessions/*/espn/*` and `/api/sessions/*/season/*` with JSON fixtures under `frontend/e2e/fixtures/season/`; the backend still serves the demo session; the draft is completed through the existing batch endpoint)
- Modify: `docs/DATA_SOURCES.md`, `docs/USER_GUIDE.md`, `docs/DECISIONS.md` (DEC-24..DEC-27 as in spec §10), `docs/PROGRESS.md`, `CLAUDE.md` (commands `make link`, `make sync`), `README.md` (one line)

- [ ] **Step 1: Write the e2e** covering: open Season on a completed session → link dialog → preview → apply → sync bar shows summary → Matchups tab shows the user card → Free agents tab lists rows → Power tab shows 13 rows.
- [ ] **Step 2: Run** `cd frontend && E2E_BACKEND_PORT=8011 E2E_FRONTEND_PORT=5177 npx playwright test e2e/season.spec.ts` → PASS.
- [ ] **Step 3: Docs** per the list; PROGRESS.md records: endpoint verified 2026-10-19, first real sync result on session 5291db641583 (counts of adds/drops), power timing from Task 6.
- [ ] **Step 4: Run** `make test` → PASS.
- [ ] **Step 5: Commit** `feat: season e2e, data source and user guide docs, DEC-24..27`.
