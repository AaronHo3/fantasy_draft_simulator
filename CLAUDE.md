# ESPN 9-cat Draft Copilot — repository instructions

Local-first draft recommendation tool for ESPN nine-category fantasy basketball. It records picks
as a manager makes them in ESPN and recommends the next pick from projections, punt strategy,
roster/position fit, scarcity, and lookahead simulation. It never submits anything to ESPN.

Stack: `backend/` Python 3.12 + FastAPI + NumPy/pandas/SciPy + SQLite (sessions) + Parquet
(snapshots), managed with `uv`. `frontend/` React 19 + TypeScript + Vite. No Redis, no cloud, no
accounts. Binds to localhost.

## Resume protocol (read before changing code)

1. Read this file, then `docs/PROGRESS.md` (status, next task, how to resume), then
   `docs/DRAFT_COPILOT_PLAN.md` (phases, acceptance criteria) and `docs/DECISIONS.md`.
2. Check `git status`; reconcile `PROGRESS.md` with the code before working.
3. Write the failing test first, implement, run `make test`, update `PROGRESS.md` before stopping.
4. Record `DEC-nn` in `docs/DECISIONS.md` for architecture or methodology changes.
5. Never label an integration, benchmark, or validation as verified unless it was actually run in
   this repo and the result is recorded in `docs/PROGRESS.md` or `docs/DATA_SOURCES.md`.

## Commands

```
make install        # uv sync (backend) + npm ci (frontend)
make dev            # backend :8000 + frontend :5173
make demo           # create a session on the labeled synthetic demo league (600 players)
make refresh        # fetch/refresh real sources into data/nba (needs internet, no credentials)
make build-snapshot # build the real projection snapshot from data/nba/normalized
make validate       # retrospective projection check -> docs/VALIDATION.md
make research       # projection model variants on two holdouts -> docs/PROJECTION_RESEARCH.md
make evaluate       # paired mock-draft strategy test -> docs/EVALUATION.md
make test           # pytest + vitest + tsc;  make e2e = Playwright full draft loop
make bench          # engine latency benchmark, writes docs/BENCHMARKS.md
make export SESSION=<id>   # portable JSON session export;  make import FILE=<json>
make link SESSION=<id> LEAGUE=<espn league id>   # map managers to a public ESPN league (read-only)
make sync SESSION=<id>     # pull rosters/matchups/transactions from ESPN; make season SESSION=<id> prints the week
```
Ports 8000/5173 may be used by other projects on this machine: `make dev BACKEND_PORT=8020 FRONTEND_PORT=5180`.

See `docs/USER_GUIDE.md` for draft-day workflow and `docs/DATA_SOURCES.md` for every source.

## Critical invariants

- FG% / FT% are always `sum(makes) / sum(attempts)` over a roster or period. Never average
  per-player percentages. Zero attempts -> `None`, handled by configured tie rule, never a win.
- Turnovers: lower is better. Every category carries an explicit `higher_is_better` flag.
- Availability of a player is derived by replaying the committed draft event log, never from a
  separately mutable list. Drafted players never appear as recommendations.
- Every recommendation response carries `draft_revision`, `strategy_revision`, `snapshot_id`,
  `projection_version`, `seed`. Clients discard responses whose revisions are stale.
- ESPN `seasonId` 2027 == NBA season `2026-27`. ESPN `defaultPositionId` is 1-indexed
  (1=PG..5=C); `eligibleSlots` are 0-indexed slot ids (0=PG,1=SG,2=SF,3=PF,4=C,5=G,6=F,7=SG/SF,
  8=G/F,9=PF/C,10=F/C,11=UTIL,12=BENCH,13=IR). Never substitute NBA roster positions for ESPN
  eligibility; unverified eligibility is flagged, not assumed.
- Fixed punts change the screening utility only; simulated matchups still score every category.
- Synthetic demo data lives under `data/demo/` and is labeled `source=demo` everywhere; it never
  mixes with real snapshots under `data/nba/` (gitignored).
- No LLM, provider fetch, or network call on the pick-commit or fast-ranking path.
- Private ESPN cookies (optional, read-only) come only from `backend/.env`; never logged,
  exported, stored in the browser, or committed. The league link reads public leagues only and never
  writes to ESPN; post-draft rosters are `roster_changed` events, never a mutable table.
- Pure ranking functions in `backend/app/engine/*` take arrays/dataclasses and return new values;
  no mutation of inputs.
