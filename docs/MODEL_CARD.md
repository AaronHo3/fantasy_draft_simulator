# Model card

Status: methodology defined; validation entries are filled in only when the experiment was run
(see PROGRESS.md for the latest run). Anything marked *provisional* has not been validated.

## 1. What is modeled

- **Per-game production** for each player in 9 categories plus primitives (MIN, GP, FGM, FGA,
  FTM, FTA, 3PM, 3PA).
- **Availability**: projected games played out of the schedule.
- **Roster value** under a league's scoring format, strategy (punts/weights), slots and schedule.
- **Draft dynamics**: which players are likely to be gone before the user's next pick.

## 2. Projection sources

0. `ens` (learned, default since DEC-20): the average of a ridge regression and a gradient-boosted
   regressor per stat on rich features (the ridge features below plus share of games at ≥ 28 / ≥ 20
   minutes, last-10-game minutes, games missed, playoff minutes, age × minutes hinges). `ridge` is the
   plain variant. Ridge regression per stat (12 per-game counting/shooting
   primitives, minutes, games) on year-to-year transitions from 2020-21 onward. Features: last season's
   per-game and per-36 numbers, the season before, minutes over the last 25 games, games-played history,
   age (with young/old hinges), team change. Penalty picked on the most recent training transition; a
   projection for season T trains only on transitions whose target precedes T. Outputs are made coherent
   (FGM ≤ FGA, 3PM ≤ min(3PA, FGM), FTM ≤ FTA, PTS derived from makes). Uncertainty: 18 % cv per stat,
   12 games sd (provisional). Players without a feature season fall back to the baseline below.
1. `baseline` (local, transparent; fallback and the opponents' model in evaluations). For each player with NBA history:
   - Per-minute rates per category from the last three regular seasons, weighted by recency
     (weights 0.6 / 0.3 / 0.1 for seasons t-1, t-2, t-3 after validation, DEC-15) and by minutes
     played.
   - Shrinkage toward a prior rate for the player's position group with pseudo-minutes `k`
     (140 minutes for counting stats, 280 for steals and blocks; shooting rates shrunk with 105 FGA,
     52 FTA, 70 3PA pseudo-attempts; constants in `projections/baseline.py`, chosen by the holdout
     grid in docs/VALIDATION.md).
   - Shooting modeled as attempt rate per minute × shrunk conversion rate (beta-binomial style),
     so FG%/FT% follow makes/attempts by construction and 3PM ≤ FGM, 3PA ≤ FGA are enforced.
   - Minutes projection: recency-weighted minutes per game shrunk toward the position-group
     median, adjusted by last-season starts share; capped at 38.
   - Games projection: recency-weighted games played shrunk toward 68 (league median of recent
     completed seasons), capped by the schedule.
   - Age curve: multiplicative adjustment to per-minute production (±1–2 % per year outside
     24–30), documented in code; small by design.
   - Uncertainty: per-player scale from year-to-year residuals of the rate model, widened for
     team change, age extremes, low minutes, and rookies.
2. `espn_projection`: ESPN's published projected season totals (public endpoint, stat split
   `102027`), divided by projected GP to per-game. Provenance label `espn`.
3. `user_import`: CSV projections (per-game, with attempts) with the user's source label.
4. `blend` (default when both 1 and 2 exist): per-game weighted average, 0.5/0.5, with the
   absolute disagreement added to the uncertainty. The weight is a build-time option
   (`build_real_snapshot(espn_weight=...)`); it is not validated because ESPN's 2026-27 projections
   cannot be scored before the season is played.

Rookies/newly active players with no NBA history: `espn_projection` discounted (× 0.85, games ≤ 65,
cv 0.35; DEC-23) if present, otherwise a draft-slot prior (minutes and rates by expected draft position tier) with wide uncertainty and a
visible "prior only" label. College statistics are not used.

Returning from a lost season (history, zero games last year): stars (30+ mpg before) games × 0.94 and
rates unchanged; role players games × 0.62 and rates × 0.75; uncertainty × 2 for both, from the 22-player 2017-2025 return sample in DEC-23. Preseason statistics are not used.

## 3. Standardization and screening value (Layer A)

- Pool: top `n_pool = managers × roster_size × 1.2` players by a first-pass unweighted value;
  recomputed once (two-pass).
- Counting categories: `(x - center) / scale` with center = median and scale = 1.4826 × MAD over
  the pool (option: mean/std). TOV is negated.
- Percentages: impact `FGM - b·FGA` and `FTM - b·FTA` with `b` = pool aggregate rate, then
  standardized like a counting stat. Volume-sensitive by construction.
- Strategy: fixed punt → weight 0; soft punt → weight (default 0.35); emphasis → user weight.
  Screening value = Σ weights × z. Then value above replacement, where replacement = the best
  available player projected to still be available at the user's next pick for a compatible slot
  need, and a slot-shortage adjustment computed from remaining supply vs. anticipated demand.

## 4. Roster utility (Layer B) and simulation (Layer C)

- Opponent rosters completed with the shared continuation policy (ADP-ordered, need-aware).
- Weekly matchup: team category totals from counted starts; each-category objective = Σ P(win cat)
  (+ ½ ties if configured); most-categories objective = P(win ≥ required categories) from the
  joint simulated outcome; roto = expected rank points by category over the league.
- Correlation: per player per week, games ~ Binomial(schedule games, availability), per-game
  stats scaled by a shared lognormal minutes/usage factor (σ=0.12, *provisional*), shooting makes
  ~ Binomial(attempts, rate).
- Common random numbers across candidates; seed carried in responses.
- Draft-now vs wait: survival probability of each shortlist player until the user's next pick
  from the opponent model; reported as a model estimate with a confidence label.

### Punt advisor
Scenario comparison, not a pick ranking: for each candidate punt set the user's remaining picks are
completed by the fast continuation policy under those weights (opponents by demand), and the finished
league is scored with the weekly simulation under the actual rules. Common random numbers across
scenarios; 6 rollouts × 150 weeks by default. The simulation layer's weakness at pick-by-pick choice
does not apply here because scenarios are averaged over many rollouts and differ by strategy, not by
one noisy pick; still, differences under two standard errors should be read as ties.

## 5. Validation

| Check | Method | Result | Status |
|---|---|---|---|
| Per-game forecast error | fit on 2023-24 + 2024-25, score 2025-26 players with ≥ 20 GP (383); MAE vs. naive last-season | PTS 2.70 vs 2.82, REB 0.86 vs 0.96, AST 0.71 vs 0.72, STL 0.203 vs 0.230, BLK 0.151 vs 0.168, 3PM 0.37 vs 0.37, TOV 0.35 vs 0.38, MIN 4.25 vs 4.60, GP 13.4 vs 16.8 | run 2026-10-09 (`make validate`, docs/VALIDATION.md) |
| Shooting calibration | attempt-weighted MAE of FG% and FT%, same holdout | FG% 0.0272 vs 0.0322 naive; FT% 0.0404 vs 0.0532 naive | run 2026-10-09 |
| ESPN projection accuracy | cannot be scored until 2026-27 is played | — | not possible yet |
| Projection model comparison | docs/PROJECTION_RESEARCH.md: four holdouts (2022-23..2025-26), Spearman of projected vs realized fantasy value (players ≥ 20 GP), ten seasons of history | ens 0.740 / 0.784 / 0.759 / 0.659; ridge 0.727 / 0.770 / 0.753 / 0.658; baseline 0.720 / 0.775 / 0.718 / 0.644 | run 2026-10-10 |
| Projection model draft edge | model-vs-model paired drafts (my seat on the learned model, opponents on baseline), 120 per year, four holdouts 2022-23..2025-26 | ens (default) +0.06 / +0.81 / +0.01 / +0.65 categories per matchup (mean +0.38, never negative); ridge −0.63 / +0.36 / +0.03 / +0.87 (mean +0.16); SE ≈ 0.1 | run 2026-10-10, docs/EVALUATION_ens_rich_*.md, EVALUATION_model_vs_model_*.md |
| Roster-aware weighting | paired drafts, fast ranking with diminishing-returns category weights vs plain, four holdouts | harmful at the natural scale (−1.23 in 2025-26), a wash at gentle scales; left off (DEC-22) | docs/EVALUATION_roster_aware_*.md |
| Games played ablation | same drafts and rankings with GP from the model vs flat / last season / 3-year average | model GP best for ranking in both years; last-season GP harmful everywhere | docs/GAMES_PLAYED_ABLATION.md |
| Ranking methods | 120 paired mock drafts per strategy (12 seats × 10 seeds), opponents = value-order bot, scored by realized 2025-26 categories won per matchup | fast ranking +0.53 ± 0.13 vs the bot, +1.0 vs last-season numbers, +0.06 ± 0.06 vs projected value alone; refined layer (2 s, 20 drafts) −0.32 ± 0.31 vs the bot | run 2026-10-10, docs/EVALUATION.md (retrospective; see caveats there) |
| Interval calibration | coverage of 80 % intervals | not yet run | *provisional* |

The retrospective experiment uses eventual games played and final rosters in its scoring, and the
preseason ADP of past seasons is not available, so it is **retrospective and potentially leaky**,
not a rigorous draft backtest.

## 6. Known limits

- No injury forecasting; injury status is a label, availability is a shrunk historical rate.
- Opponent behavior is a simple ADP + need model; survival probabilities are estimates.
- Daily-lineup leagues are approximated by per-day assignment under a game cap, not real
  streaming behavior.
- Simulated win rates are statements about the simulator's assumptions.
