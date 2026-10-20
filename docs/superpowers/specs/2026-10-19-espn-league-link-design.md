# ESPN league link and in-season tracking — design

Date: 2026-10-19. Status: approved in chat by the user (Aaron Ho); builder check done, five
open points settled as builder's calls (listed at the end).

## Intent

The draft is over. The user's league ("1000Thieves", ESPN league id 2075231076, 13 teams, H2H each
category, 8 categories without turnovers) now changes every day through adds, drops and trades, and
every week through matchup pairings. Until now every post-draft analysis (power rankings, matchup
odds, free-agent advice) was computed from hand-typed rosters. The user wants the app to read the
league from ESPN itself so rosters, matchups and free agency stay current without re-listing teams.

The user made the league publicly viewable, so the read endpoint works with no cookies:

    GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/2027/segments/0/leagues/2075231076
        ?view=mTeam&view=mRoster&view=mSettings&view=mMatchup&view=mSchedule&view=mTransactions2&view=mStatus

Verified from this machine on 2026-10-19 (HTTP 200): settings, 13 teams with rosters (171 players,
all present in the current projection snapshot by `espn_id`), members with first/last names, the 19
matchup periods (133 pairings, one bye per week because 13 teams), 263 transactions. A private league
returns 401; cookies stay an optional later step.

## Goals

1. **Link once, sync on demand.** Link a session to an ESPN league id; a sync pulls everything in
   one request and records roster differences as events. Manual sync button and CLI; optional
   auto-refresh while the Season screen is open.
2. **Rosters follow ESPN.** Every analysis uses the current ESPN roster of every team, including IR.
3. **Matchups.** Show the week's pairings with projected per-category win odds for each pair, and the
   user's next opponent with the full category breakdown.
4. **Power rankings.** Expected categories per week vs the field for all teams, with movement since
   the previous sync.
5. **Free agency.** Rank unowned players by what they add to the user's team, with the best drop
   candidate for each.
6. **Results.** Once games are played, show ESPN's actual per-category weekly results beside the
   projection.

## Non-goals and anti-goals

- No writes to ESPN, ever (no lineup changes, no claims). Read-only link.
- No cookies in this iteration. Private-league support stays behind `COPILOT_ESPN_SWID` /
  `COPILOT_ESPN_S2` and is not built here.
- Do not rewrite the draft session into ESPN's team ids. Session manager ids (`m01`..`m13`) stay;
  the link stores a mapping.
- Do not change the recommendation engine or the projection model.
- Anti-goal: silent roster edits. Every change the sync applies is an event with a source and a
  summary the user can read in the history drawer.
- Anti-goal: a sync that fails half-way and leaves rosters inconsistent. One sync = one batch append,
  all-or-nothing.

## Constraints (from CLAUDE.md invariants)

- Availability and rosters are derived by replaying the event log. Post-draft rosters therefore need
  new event types; no separately mutable roster table.
- Every response carries `draft_revision` etc.; sync bumps `draft_revision` because rosters changed.
- FG%/FT% from summed makes/attempts; TOV absent in this league (categories come from the session).
- No network call on the ranking path: sync is an explicit action; analytics read the stored state.
- Pure functions in `engine/` and parsers in `sources/` take data and return new values.
- ESPN seasonId 2027 == NBA 2026-27. Player identity by ESPN `playerId` → snapshot `espn_id`.

## Design

### 1. Source adapter: `backend/app/sources/espn_league.py`

Pure parsers over the league JSON plus one fetch function, following `espn_public.py`
(`_get`, `with_retries`, `SchemaError`, `RawResponse`). Raw body cached to
`data/nba/raw/espn_league/<league_id>/<fetched_at>.json` like other sources (gitignored).

- `fetch_league_raw(league_id, season_id, client=None) -> RawResponse` with the view list above.
- Sync makes **two** cookie-less requests: the league (above) and the existing
  `espn_public.fetch_players_raw` for live status of the whole player pool (injury status,
  percent owned, NBA team). The second feeds a small `live_status` table (espn_id → status,
  percent_owned, team, fetched_at) written to `data/nba/live/<league_id>/players.parquet` and read
  by the free-agent and matchup endpoints. It never modifies the immutable snapshot; it overlays
  status at analysis time. If it fails, sync still completes with a warning and the snapshot's
  status is used.
  401/403 → `LeagueAccessError("league is private; make it viewable to public or add cookies")`.
- `parse_league(payload) -> EspnLeague` (frozen dataclasses):
  - `settings`: name, scoring_type, stat ids, lineup slot counts, position limits, lineup lock type,
    matchup_period_count, playoff_team_count, current_matchup_period, scoring_period_id.
  - `teams`: id, abbrev, name, owner member ids, owner display name ("First Last" from `members`),
    `roster: tuple[EspnRosterEntry]` (espn_player_id, name, lineup_slot_id, injury_status,
    acquisition_type), record (w/l/t), playoff seed, waiver rank.
  - `matchups`: id, matchup_period_id, home_team_id, away_team_id (None = bye), winner,
    per-stat score and result for each side from `cumulativeScore.scoreByStat` (stat id → score,
    result WIN/LOSS/TIE/None).
  - `transactions`: id, type (FREEAGENT/WAIVER/ROSTER/TRADE_ACCEPT/...), status, team_id,
    proposed_at (ISO), items (ADD/DROP/TRADE with player id, from/to team). LINEUP and DRAFT items
    are parsed but flagged `is_roster_move=False`.
- `settings_diff(espn_settings, league_config) -> list[str]`: human-readable differences (scoring
  type, category set, slot counts, C cap, lineup lock type). Shown as warnings, never auto-applied.
  Known today: ESPN says `lineupLocktimeType=INDIVIDUAL_GAME` (daily locks) while the session says
  weekly; the warning will surface this and the user decides.

### 2. Team mapping: `backend/app/season/link.py`

`match_teams(state, espn_league, snapshot) -> TeamMapping` maps each session manager to one ESPN
team by **roster overlap** (share of the manager's drafted players that sit on the ESPN roster,
resolved as a maximum-weight assignment; ties broken by normalized owner-name similarity), with
`confidence` per pair and `unmatched` lists. Overlap is the robust key because the draft just
happened and names differ ("Kurdi" vs "Abdullah Alkurdi", "Tim Wu" vs "Timothy Wu"). The user can
override any pair in the link dialog. The mapping is stored on `LeagueConfig`:

```
espn_league_id: int | None = None
espn_team_ids: dict[str, int] = {}      # manager_id -> ESPN team id
espn_linked_at: str | None = None
```

via the existing `league_updated` event (no new event type for linking).

### 3. Roster events and state: `backend/app/draft/events.py`

New event type `roster_changed`, allowed only when `state.is_complete`. One event carries every
move of one sync (or one manual edit) so a trade is a single atomic event:

```
payload = {
  "moves": [
    {"manager_id": "m10", "added": ["nba:4278129"], "dropped": ["nba:4601023"],
     "source_ref": "espn:<transaction id>" | "espn:roster-diff" | "manual"},
    {"manager_id": "m12", "added": ["nba:4601023"], "dropped": ["nba:4278129"], ...}
  ],
  "effective_at": "2026-10-18T22:19:36Z",
  "note": "ESPN sync 2026-10-19T03:10Z"   # optional
}
```

Rules in `apply`: all drops in the event are applied first, then all adds. A player can only be
dropped by the manager who owns him; after the drops, an added player must be unowned; the same
player cannot be added by two managers in one event. Violations raise
`DraftError("roster_conflict", ...)` and the whole event is rejected. `pick_undone` and
`pick_corrected` are rejected once any `roster_changed` exists (`DraftError("draft_locked")`).

`DraftState` gains `moves: tuple[RosterMove, ...]` (flattened, in seq order) and:

- `owned_player_ids` (frozenset): drafted − dropped + added, replayed in seq order.
- `current_roster(manager_id) -> tuple[str, ...]`: draft picks in pick order minus drops, plus adds
  in event order.
- `current_rosters()`.

`drafted_player_ids` keeps its meaning for the draft. After the draft, the recommendation service's
notion of "available" switches to `owned_player_ids` so the existing fast ranking works for free
agents unchanged (one line in `user_context`).

Sync also records `league_updated` when the ESPN team mapping changes. A sync with no roster
difference writes **no events** (so auto-refresh never churns `last_seq` or invalidates client
state). The sync bookkeeping that is not league truth (fetched_at, change summary, the power table
at that moment for "movement since last sync", settings warnings) lives in a new `session_sync`
table in the sessions SQLite file, one row per session, overwritten on every sync. It is a cache:
deleting it loses only the movement arrows.

### 4. Sync service: `backend/app/season/sync.py`

`plan_sync(state, espn_league, snapshot, mapping) -> SyncPlan` (pure):

- For each mapped manager, diff `state.current_roster(m)` against the ESPN roster (by canonical id
  through `espn_id`). Produce one `roster_changed` payload per manager with both lists.
- Attribute each add/drop to an ESPN transaction when one matches (player id + team id + executed);
  otherwise `source_ref="espn:roster-diff"`.
- Unknown ESPN players (not in snapshot) go to `warnings` and are added with id `espn:<id>` and a
  zero projection row at analysis time (they still count as owned so they are not free agents).
- `settings_diff` warnings, mapping warnings, and "ESPN shows N IR slots" notes.

`apply_sync(store, session_id, plan)` appends the events in one `append_batch` with
`expected_revision` so two concurrent syncs cannot double-apply; idempotency key
`espn-sync:<session>:<fetched_at>`.

Sync history: the last sync's `fetched_at`, change summary and power rankings are stored as a
`note` event payload so "movement since last sync" is derivable from the log, not from memory.

### 5. Season analytics: `backend/app/season/power.py`

Pure functions over `(snapshot, league, rosters, seed)`; reuse `simulate_players_week`,
`team_totals(max_starters=len(starting_slots))` (weekly lock) or daily weights if the league is
daily, `category_outcomes`, `each_category` tie credit 0.5. Default 600 scenarios, common random
numbers across teams (one player-week simulation shared by every pairing, as the matchup analyses
in this session did).

**Games and availability (methodology, DEC-27):**
- *Power rankings* use the season projection: projected games per week from
  `snapshot.team_games_per_week`, projected GP for availability. Players in an ESPN IR slot are
  excluded from the counted starters; everyone else counts by projected minutes.
- *Matchup odds for a specific period* use the **actual NBA games in that period** from
  `data/nba/normalized/schedule.parquet` (fetched by `make refresh`; one row per game with date and
  ESPN scoring period id). Matchup period k covers the Monday-anchored week k of the regular season
  (period 1 = 2026-10-20..2026-10-26, confirmed against ESPN's `matchupPeriodCount=19` and the
  schedule); each player's games that week = his team's games in the window. Players ESPN marks
  OUT or in an IR slot play zero games that week; DAY_TO_DAY players keep their projected
  availability. If the schedule parquet is missing, fall back to season averages and say so in
  `notes`.
- The schedule table is loaded lazily once per process and cached on the app context.

- `power_rankings(...) -> list[TeamPower]`: expected categories per week vs the field (mean over the
  12 opponents), per-category win probability vs the field, team z profile (season totals,
  top-10 by minutes), rank.
- `matchup_odds(a, b) -> MatchupOdds`: expected categories for each side, P(win week), P(tie),
  P(loss), per-category P(a wins), most likely score line.
- `free_agents(...) -> list[FreeAgentView]`: for every unowned player with a projection (live
  status overlay: OUT/IR players shown but sorted below with a flag; percent owned shown), value =
  the existing Layer A score with the user's current roster (`rank_layer_a` through
  `user_context`), plus `best_drop`: the roster player whose removal costs the least weighted z
  (ties → lowest projected minutes), and the net team-z delta of the swap. Filter: injury status
  shown, IR-eligible flagged.
- `week_results(espn_league, period, mapping)`: actual per-category scores and results straight
  from ESPN's `scoreByStat`, mapped to session categories by stat id (0 PTS, 6 REB, 3 AST, 2 STL,
  1 BLK, 17 3PM, 19 FG%, 20 FT%); plus projected odds for the same pairing for comparison. Replaces
  the nba_api-based tracker for standings; the tracker's player-line sheet stays for `make season`.

Runtime target: a full overview (13 power rows + 6 matchups) under 2 s on this machine with 600
scenarios; the free-agent ranking is Layer A and is instant.

### 6. API (`routes.py`, `schemas.py`)

```
POST /sessions/{id}/espn/link       {league_id, overrides?: {manager_id: team_id}}
                                    -> LinkPreview {teams, mapping (manager, team, confidence),
                                       unmatched, settings_warnings}  (no events written)
POST /sessions/{id}/espn/link/apply {league_id, mapping}
                                    -> SessionDetail (league_updated appended)
POST /sessions/{id}/espn/sync       {expected_revision?}
                                    -> SyncResult {fetched_at, changes[], warnings[], state}
GET  /sessions/{id}/season/overview ?seed= -> SeasonOverview {synced_at, current_period,
                                       power[], matchups[] (this period), user_matchup, movement}
GET  /sessions/{id}/season/matchup  ?period=&team_a=&team_b= -> MatchupOdds
GET  /sessions/{id}/season/free-agents ?limit=50&position=&q= -> FreeAgentView[]
GET  /sessions/{id}/season/results  ?period= -> WeekResults
```

All responses carry the usual `ResponseIds`. Sync and link validate `league_id` (positive int) and
run the network call outside the ranking path. Network errors map to 502 with ESPN's status;
401/403 → 409 `league_private` with the two fixes in the message.

### 7. CLI and Makefile

- `python -m app.cli espn-link SESSION LEAGUE_ID [--map m10=7 ...]` prints the mapping preview and
  applies with `--apply`.
- `python -m app.cli espn-sync SESSION` prints the changes.
- `python -m app.cli season SESSION` now prints the ESPN-based week results when linked, falling
  back to the nba_api tracker when not.
- `make link SESSION=<id> LEAGUE=<id>`, `make sync SESSION=<id>`.

### 8. Frontend

- New route `season` and `SeasonScreen.tsx`; nav shows "Season" once the draft is complete.
- `seasonStore.ts` (zustand): overview, matchups, free agents, results, sync status, auto-refresh
  interval (off / 15 min / 60 min; default off, remembered in localStorage).
- Components under `components/season/`:
  - `SyncBar`: "Linked to 1000Thieves · synced 12 min ago · [Sync now] · auto-refresh select",
    last changes summary, warnings (settings diff).
  - `LinkDialog`: league id input, mapping table (manager ↔ ESPN team, confidence, override
    select), settings warnings, Apply.
  - `MatchupsTab`: this week's pairings as cards; the user's card first with the category odds
    grid (same visual language as `CategoryProfileTable`); period selector.
  - `PowerTab`: ranked table with expected cats/week, per-category win chance bars, Δ since last
    sync.
  - `FreeAgentsTab`: table of free agents with value, category deltas, best drop and net delta,
    position/injury filters, search; click opens `PlayerDrawer`.
  - `ResultsTab`: ESPN actuals per category for the chosen period next to projected odds.
- The existing `TeamsPanel`/`OpponentRosters` read `current_rosters` so post-draft rosters show
  adds; the history drawer renders `roster_changed` events.

### 9. Tests

- Parser tests on a trimmed fixture (`backend/tests/fixtures/espn_league_small.json`: 3 teams,
  2 periods, 5 transactions) covering settings, rosters, byes, scoreByStat, add/drop items.
- Events: roster_changed replay, ownership conflicts, `current_roster` ordering, draft-only guard.
- Link: roster-overlap matching with renamed owners and one swapped team; override path.
- Sync: plan diff with adds/drops/unknown players and a two-team trade in one event; idempotent
  re-sync produces zero events; `session_sync` row updated anyway.
- Power/matchup/free agents: deterministic with seed; symmetric odds (P(a)+P(b)+tie = 1); free
  agents exclude owned players; best-drop never the top-minutes starter when a bench player exists.
- API: link preview/apply/sync/overview with the fetch mocked; 401 → 409.
- Frontend: store tests for sync status and auto-refresh timer; e2e `season.spec.ts` with the API
  mocked at the network layer (Playwright route) covering link → sync → matchups → free agents.

### 10. Docs

- `docs/DATA_SOURCES.md`: the league endpoint, verified date, field map.
- `docs/USER_GUIDE.md`: in-season section.
- `docs/DECISIONS.md`: DEC-24 (roster events, not a roster table), DEC-25 (team mapping by roster
  overlap), DEC-26 (ESPN actuals replace nba_api standings when linked), DEC-27 (week odds use the
  real schedule and ESPN injury status; power rankings use season averages).
- `docs/PROGRESS.md`.

## Left to the builder

- Exact dataclass field names, schema names, and the layout of the Season screen within the
  existing token system (`styles/index.css`).
- Fixture trimming script.
- Whether `free_agents` caches the Layer A standardization per state revision (recommended).

## My calls (not the user's)

- Roster-overlap mapping rather than owner names.
- `roster_changed` as one event per sync carrying every manager's moves (drops before adds), so a
  trade is atomic; not one event per transaction.
- Matchup odds for a period use the real NBA schedule for that week; power rankings use season
  averages. ESPN OUT/IR players play zero games in the week odds; IR players never count as
  starters.
- Sync also refreshes the public ESPN player feed so free-agent status and percent owned are live;
  the snapshot itself stays immutable.
- A no-change sync writes no events; sync bookkeeping lives in a `session_sync` cache table.
- Auto-refresh off by default; manual sync is the primary path.
- Daily-vs-weekly lock mismatch is surfaced, not auto-applied.
- Unknown players are kept as owned placeholders with zero projection rather than dropped.
