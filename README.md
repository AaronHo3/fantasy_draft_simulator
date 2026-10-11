# ESPN 9-cat Draft Copilot

Designed to be a fun side project to help aid in making decisions for my ESPN fantasy league with friends.

A local-first draft assistant for ESPN nine-cat fantasy basketball. You record picks as they happen during the draft and get a ranked, explained shortlist for your next pick. It explains who adds the most value above the player you could still get next turn, which lineup slot they fill, what they add to each of the nine categories, and how likely they are to be gone before you pick again.

Under the hood, it builds its own player projections from ten seasons of NBA data (a learned model, validated on four held-out seasons and blended with ESPN's published projections), applies the league's exact rules (ESPN eligibility, roster slots, position caps, tie handling, punts), and runs a Monte Carlo draft-and-matchup simulation for lookahead and a punt advisor. 

In paired mock drafts on past seasons, the recommendations beat ADP-style drafting by about half a category per weekly matchup. 

Runs entirely on your laptop with no accounts and no ESPN credentials (FastAPI + React), also works offline once data is cached. 


```
make install        # uv sync + npm ci
make demo           # create a session on the synthetic 600-player demo league
make dev            # backend :8000 + frontend :5173 (override: BACKEND_PORT=... FRONTEND_PORT=...)
make refresh        # real data: nba_api + ESPN public endpoints (~12 requests, no cookies)
make build-snapshot # projections + eligibility + ADP -> data/nba/snapshots/
make test           # pytest + vitest + tsc
make e2e            # Playwright: full draft loop against a real backend
make bench          # latency benchmarks -> docs/BENCHMARKS.md
make validate       # projection holdout check -> docs/VALIDATION.md
```

Docs: `CLAUDE.md` (invariants, resume protocol), `docs/USER_GUIDE.md`, `docs/DRAFT_COPILOT_PLAN.md`,
`docs/DECISIONS.md`, `docs/DATA_SOURCES.md`, `docs/MODEL_CARD.md`, `docs/PROGRESS.md`,
`docs/BENCHMARKS.md`, `docs/VALIDATION.md`.
