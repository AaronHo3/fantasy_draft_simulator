# Draft Copilot plan

Status legend: `[x]` done and tested, `[~]` partially done, `[ ]` planned, `[!]` blocked. Updated 2026-10-10.
Current status is mirrored in `PROGRESS.md`; this file holds the architecture and the task list.

## 1. Goal

A localhost web app that lets one manager run an ESPN nine-category (9-cat) snake draft: record
every pick, see availability update instantly, and get a ranked, explained shortlist for the next
pick that respects punts, category weights, ESPN eligibility, roster feasibility, scarcity, and
likely availability at the manager's next turn. Works offline from cached data. Never submits
anything to ESPN.

## 2. Architecture

```
frontend/ (React 19 + TS + Vite)         backend/ (FastAPI, Python 3.12, uv)
 ├─ draft screen (board, picker,          ├─ app/api/        routers + pydantic schemas (OpenAPI)
 │  shortlist, roster, categories,        ├─ app/draft/      event log, replay, pick schedule
 │  strategy panel)                        ├─ app/league/     league config, slots, scoring formats
 ├─ setup/import, data health,            ├─ app/engine/     pure numerics:
 │  compare, recap                         │    categories.py   9-cat totals, FG%/FT%, z-values
 ├─ zustand store + revision guard         │    lineup.py       bipartite slot matching, caps
 └─ generated API types (openapi-ts)       │    replacement.py  replacement/scarcity pools
                                           │    layer_a.py      fast screening utility
                                           │    layer_b.py      roster-aware marginal utility
                                           │    layer_c.py      Monte Carlo draft + matchup sim
                                           │    opponents.py    opponent demand + completion
                                           ├─ app/projections/ baseline model, ESPN proj, overrides
                                           ├─ app/sources/    nba_api, espn public, csv import
                                           ├─ app/identity/   canonical ids + crosswalk
                                           ├─ app/persistence/ SQLite (sessions, events), parquet
                                           ├─ app/recommend/  orchestration, jobs, caching
                                           └─ app/demo/       synthetic 600-player fixture
data/
 ├─ demo/        committed synthetic fixtures (source=demo)
 ├─ nba/         real snapshots (gitignored): raw/, normalized/, derived/
 └─ sessions/    SQLite session DBs (gitignored)
```

Request flow during a draft:

1. User confirms a pick -> `POST /sessions/{id}/events` (idempotency key, expected revision).
   Backend appends to the event log, replays state, returns new `draft_revision`. Frontend applies
   the pick optimistically first (target ~100 ms visible update).
2. Frontend asks `POST /sessions/{id}/recommend/fast` -> Layer A over all available players
   (vectorized NumPy; target p95 < 250 ms). Response carries revision ids.
3. Frontend asks `POST /sessions/{id}/recommend/refine` -> returns a job id; Layer B/C runs in a
   thread executor under a wall-clock budget; `GET /jobs/{id}` polls. Results tagged with the same
   revision ids; stale results are discarded client-side and server-side.
4. Strategy changes are events too (`strategy_changed`) and bump `strategy_revision`.

## 3. Key design points

- **Scoring formats**: `h2h_each_category`, `h2h_most_categories`, `roto`. Each has its own
  objective in Layer B/C. Default preset is H2H Most Categories with a mandatory "confirm format"
  banner. Ties configurable (`tie_counts_as`: `none|half|win_for_lower_seed_n/a`).
- **Positions**: three separate concepts: ESPN primary position (`defaultPositionId`), ESPN
  eligible slots, and league lineup slots. Lineup legality is bipartite matching
  (`scipy.optimize.linear_sum_assignment` on a cost matrix with dummy nodes). Primary-position
  caps apply separately. Completion feasibility checks remaining picks against open slots.
- **9-cat math**: counting totals summed over counted starts; FG%/FT% from summed makes/attempts;
  volume-sensitive impact `FGM - b*FGA` for screening; robust z (median/MAD or trimmed mean/std,
  configurable) over a fantasy-relevant pool (top `N_pool = managers * starters * 1.25` by
  minutes-weighted value, iterated once).
- **Projections**: baseline = recency-weighted per-minute rates (3 seasons, weights validated),
  shrunk to position/role priors, times projected minutes and games; shooting via attempt rates
  and shrunk conversion. ESPN's public projected totals (split `10{season}`) are an alternate
  source labeled `espn_projection`; the default blend and its weights are documented in
  `MODEL_CARD.md`. Rookies: ESPN projection if present, otherwise draft-slot prior with wide
  uncertainty. Manual overrides keep original + history.
- **Layers**: A = punt-weighted standardized value + shooting impact + availability + replacement
  + slot-shortage adjustment. B = roster category utility vs. opponent distribution with a
  consistent completion policy for all remaining picks (candidate vs. best-alternative baseline,
  equal roster sizes). C = Monte Carlo: opponent picks until my next turn (ADP-driven, needs-
  aware), my continuation policy, weekly matchup simulation with correlated per-player outcomes
  (shared minutes/games factors), scoring under the actual format rules; common random numbers
  across candidates.
- **Opponent model**: ADP (ESPN, platform-labeled) + positional need + noise. Survival
  likelihoods are shown as model estimates with a "proxy" label when ADP coverage is thin.
- **Persistence**: SQLite tables `sessions`, `events` (append-only, `seq`, `idempotency_key`
  unique), `snapshots_meta`, `source_runs`. State = replay(events). Export = JSON with schema
  version and full event history.
- **Offline**: all real data lands in `data/nba/` parquet snapshots; the app starts from the last
  good snapshot; demo fixture always available.

## 4. Phases and tasks

### Phase 0 — inspect, plan, scaffold
- [x] Inspect repository (empty) and tooling; probe sources with their own clients.
- [x] Write CLAUDE.md, this plan, DECISIONS, DATA_SOURCES, MODEL_CARD, PROGRESS, USER_GUIDE.
- [x] Scaffold backend (uv, FastAPI) and frontend (Vite React TS), Makefile, .gitignore.

### Phase 1 — manual draft loop (core MVP)
- [x] League config model (categories, format, managers, slots, draft order, caps, bench, keepers).
- [x] Snake/edited pick schedule, next-turn distance, keepers, traded picks.
- [x] Event log + replay (pick_committed, pick_undone, pick_corrected, keeper_assigned,
      order_changed, strategy_changed), idempotency, optimistic concurrency, SQLite persistence.
- [x] Canonical player table + CSV import (projections, eligibility, ADP, picks) with preview.
- [x] Synthetic demo dataset (~600 players, 12 teams, labeled demo) + demo league.
- [x] Baseline category rankings (Layer A, no punts) and player search.
- [x] API: sessions, events, players, recommend/fast, export/import.
- [x] Frontend: setup, draft screen (board, picker, shortlist, roster), undo/correct.
- [x] E2E: setup -> opponent picks -> my pick -> updated suggestions -> undo -> reload.

### Phase 2 — real data, projections, eligibility
- [x] nba_api adapter: active players, 3 seasons totals + game logs, raw/normalized parquet,
      retries/backoff/timeouts, source runs, data health.
- [x] ESPN public adapter: players (eligibility, ADP, ranks, projections), schedule by scoring
      period; season mapping; no credentials.
- [x] Identity crosswalk NBA id <-> ESPN id (exact id where available, normalized name+team,
      ambiguous -> review queue).
- [x] Baseline projection model + ESPN projection source + blend + overrides.
- [x] Exact percentage math, coherence validation, data health view.

### Phase 3 — strategy, feasibility, deterministic roster utility
- [x] Fixed/soft punts, user weights, balanced mode, suggested punts (opt-in, never auto).
- [x] Lineup matching, primary caps, completion feasibility, coverage quality.
- [x] Replacement/scarcity from remaining compatible players and league demand.
- [x] Format-correct deterministic roster utility (Layer B).

### Phase 4 — simulation and lookahead
- [x] Opponent completions, ADP demand model, picks-until-my-turn rollouts.
- [x] Correlated weekly scenarios, counted starts (weekly lock; daily collision approximation only).
- [x] Shortlist Monte Carlo (Layer C), draft-now vs wait, tiers/uncertainty, bounded async jobs.

### Phase 5 — UI polish and optional ESPN read-only import
- [x] Compare, scenario preview, before/after deltas, keyboard flow, source labels, recovery.
- [~] Optional read-only ESPN league import (settings, draft results) behind env cookies: implemented and
      unit-tested, NOT verified against a real league; live sync unsupported.

### Phase 6 — verification
- [x] Unit/integration tests per `DRAFT_COPILOT_PLAN.md` §5, E2E, 600-player benchmark.
- [x] Retrospective evaluation 2023-24+2024-25 -> 2025-26 (labeled retrospective, not leak-free). Paired
      mock-draft comparison of ranking methods: [x] run 2026-10-10 (docs/EVALUATION.md).
- [x] Docs reconciled with evidence.

## 5. Acceptance criteria (from the brief)

1. Custom 9-cat league + complete manual draft without ESPN credentials.
2. Committed picks immediately change availability/recommendations; drafted players never
   recommended.
3. Punts, weights, and ESPN eligibility change rankings with computed explanations.
4. FG%/FT% via makes/attempts; TOV reversed; semantics match the format.
5. Coverage via legal assignment + completion checks.
6. Provenance, freshness, assumptions, demo status visible.
7. Offline operation; state survives reload, undo, corrections, export/import.
8. Simulation never blocks pick entry; no stale recommendation shown as current.
9. Measured performance and verification documented; no fabricated numbers.
10. Optional integrations failing never break the manual core.
