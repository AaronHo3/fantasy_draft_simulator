# Draft strategy evaluation (retrospective mock drafts)

Generated 2026-10-10T19:18:26+00:00. Target season 2025-26; 12-team snake, 13 rounds, H2H each category with ties worth half, 10 starters, four-center cap. Every strategy drafts from the same seat with the same opponent randomness; the other 11 teams draft by value order with positional need and noise.

**Read this first.** Universe: 387 players with NBA history before 2025-26 and an ESPN eligibility link (2025 rookies excluded: no leak-free projection exists for them). Eligibility comes from the current ESPN snapshot (not the preseason of the target year). Opponents draft by value order with positional need and noise; no historical ADP is available, so draft dynamics are a proxy. Players who did not play in the target season score zero (injuries count against every strategy equally). Counted starters: top 10 roster players by realized minutes (weekly-lock proxy).

Scoring: the completed roster's realized season totals (top 10 by minutes) against each of the 11 other teams in the same draft, categories won per matchup (0–9, ties half), its win rate (> 4.5 categories), and its rank in that league.

## Strategies

- `adp_bot`: the same policy the opponents use (value order + need + noise).
- `naive_last_season`: best available by last season's per-game numbers (no projection model).
- `static_value`: best available by projected season value (unweighted z-sum), no roster logic.
- `static_need`: static value restricted to players who fill an open starting slot.
- `fast`: the copilot's fast ranking (strategy-weighted value above replacement at the following pick, feasibility).
- `refined`: the copilot's refined layer (draft rollouts + weekly matchup simulation; marginal categories won).

## Results per strategy

| strategy | drafts | categories won / matchup | matchup win rate | mean league rank (of 12) | top-3 finishes |
|---|---|---|---|---|---|
| adp_bot | 120 | 4.50 | 50.0% | 6.5 | 25% |
| fast | 120 | 5.03 | 62.7% | 4.8 | 47% |
| naive_last_season | 120 | 3.96 | 31.9% | 8.4 | 4% |
| refined | 20 | 4.25 | 42.3% | 7.1 | 25% |
| static_need | 120 | 4.95 | 61.1% | 4.9 | 51% |
| static_value | 120 | 4.97 | 61.6% | 4.9 | 48% |

## Paired differences vs `adp_bot` (same seat, same seed)

| strategy | pairs | Δ categories won | ± SE | better / worse / equal | Δ rank |
|---|---|---|---|---|---|
| fast | 120 | +0.53 | 0.13 | 79 / 34 / 7 | -1.7 |
| naive_last_season | 120 | -0.54 | 0.11 | 39 / 79 / 2 | +1.9 |
| refined | 20 | -0.32 | 0.31 | 8 / 12 / 0 | +0.9 |
| static_need | 120 | +0.45 | 0.13 | 74 / 43 / 3 | -1.6 |
| static_value | 120 | +0.47 | 0.13 | 76 / 42 / 2 | -1.6 |

## Paired differences vs `static_value` (same seat, same seed)

| strategy | pairs | Δ categories won | ± SE | better / worse / equal | Δ rank |
|---|---|---|---|---|---|
| adp_bot | 120 | -0.47 | 0.13 | 42 / 76 / 2 | +1.6 |
| fast | 120 | +0.06 | 0.06 | 47 / 38 / 35 | -0.1 |
| naive_last_season | 120 | -1.01 | 0.11 | 27 / 93 / 0 | +3.4 |
| refined | 20 | -0.20 | 0.25 | 8 / 11 / 1 | +0.6 |
| static_need | 120 | -0.02 | 0.02 | 9 / 16 / 95 | -0.0 |

A difference is meaningful when it is at least two standard errors from zero. Simulated and retrospective results describe this experiment's assumptions, not guaranteed draft outcomes.

Raw results: `docs/EVALUATION.json`.
