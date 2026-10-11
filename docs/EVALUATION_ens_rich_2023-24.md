# Draft strategy evaluation (retrospective mock drafts)

Generated 2026-10-10T22:59:08+00:00. Target season 2023-24; 12-team snake, 13 rounds, H2H each category with ties worth half, 10 starters, four-center cap. Every strategy drafts from the same seat with the same opponent randomness; the other 11 teams draft by value order with positional need and noise.

**Read this first.** Universe: 271 players with NBA history before 2023-24 and an ESPN eligibility link (2025 rookies excluded: no leak-free projection exists for them). Eligibility comes from the current ESPN snapshot (not the preseason of the target year). Opponents draft by value order with positional need and noise; no historical ADP is available, so draft dynamics are a proxy. Players who did not play in the target season score zero (injuries count against every strategy equally). Counted starters: top 10 roster players by realized minutes (weekly-lock proxy).

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
| alt_model | 120 | 5.82 | 91.7% | 1.8 | 92% |
| static_value | 120 | 5.01 | 66.1% | 4.6 | 46% |

## Paired differences vs `adp_bot` (same seat, same seed)

| strategy | pairs | Δ categories won | ± SE | better / worse / equal | Δ rank |
|---|---|---|---|---|---|
| alt_model | 120 | +1.32 | 0.09 | 107 / 12 / 1 | -4.7 |
| static_value | 120 | +0.51 | 0.10 | 89 / 29 / 2 | -1.9 |

## Paired differences vs `static_value` (same seat, same seed)

| strategy | pairs | Δ categories won | ± SE | better / worse / equal | Δ rank |
|---|---|---|---|---|---|
| adp_bot | 120 | -0.51 | 0.10 | 29 / 89 / 2 | +1.9 |
| alt_model | 120 | +0.81 | 0.08 | 95 / 20 / 5 | -2.8 |

A difference is meaningful when it is at least two standard errors from zero. Simulated and retrospective results describe this experiment's assumptions, not guaranteed draft outcomes.

Raw results: `docs/EVALUATION_ens_rich_2023-24.json`.
