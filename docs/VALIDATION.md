# Projection validation (retrospective)

Generated 2026-10-10T01:51:51+00:00. Target season 2025-26, fit seasons 2023-24, 2024-25, 383 players with >= 20 GP in the target season.

**Caveat.** Retrospective: scored on players who actually played >= min_gp games in the target season (survivorship), with final rosters known; preseason ADP/eligibility of the target season were not used. Not a leak-free draft backtest.

## Mean absolute error of per-game projections (FG%/FT% attempt-weighted)

| variant | PTS | REB | AST | STL | BLK | FG3M | TOV | FGA | FTA | MIN | GP | FG_PCT | FT_PCT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| naive_last_season | 2.82 | 0.96 | 0.72 | 0.23 | 0.17 | 0.37 | 0.38 | 2.06 | 0.73 | 4.60 | 16.80 | 0.032 | 0.053 |
| baseline_default | 2.70 | 0.86 | 0.71 | 0.20 | 0.15 | 0.37 | 0.35 | 1.94 | 0.74 | 4.25 | 13.36 | 0.027 | 0.040 |
| baseline_k_x0.5 | 2.67 | 0.85 | 0.70 | 0.20 | 0.15 | 0.36 | 0.36 | 1.92 | 0.72 | 4.25 | 13.36 | 0.028 | 0.040 |
| baseline_k_x2 | 2.75 | 0.88 | 0.73 | 0.21 | 0.16 | 0.38 | 0.35 | 1.96 | 0.76 | 4.25 | 13.36 | 0.028 | 0.042 |
| baseline_w_0.7_0.3 | 2.69 | 0.85 | 0.70 | 0.20 | 0.15 | 0.36 | 0.35 | 1.93 | 0.73 | 4.22 | 13.36 | 0.027 | 0.040 |
| baseline_w_0.4_0.4_0.2 | 2.76 | 0.88 | 0.74 | 0.20 | 0.15 | 0.38 | 0.36 | 1.98 | 0.75 | 4.35 | 13.54 | 0.028 | 0.040 |

## Mean bias (projection − actual)

| variant | PTS | REB | AST | STL | BLK | FG3M | TOV | FGA | FTA | MIN | GP | FG_PCT | FT_PCT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| naive_last_season | -0.25 | +0.09 | -0.10 | -0.01 | +0.02 | -0.00 | -0.02 | +0.00 | -0.19 | +0.05 | -2.56 | -0.007 | -0.010 |
| baseline_default | +0.16 | +0.24 | +0.01 | +0.00 | +0.05 | +0.04 | +0.01 | +0.27 | -0.14 | +1.18 | +5.25 | -0.002 | -0.001 |
| baseline_k_x0.5 | +0.08 | +0.24 | -0.01 | +0.01 | +0.05 | +0.03 | +0.01 | +0.22 | -0.16 | +1.18 | +5.25 | -0.002 | -0.002 |
| baseline_k_x2 | +0.26 | +0.25 | +0.03 | +0.00 | +0.05 | +0.05 | +0.02 | +0.33 | -0.12 | +1.18 | +5.25 | -0.001 | -0.000 |
| baseline_w_0.7_0.3 | +0.13 | +0.23 | -0.00 | +0.00 | +0.05 | +0.04 | +0.01 | +0.24 | -0.15 | +1.11 | +4.89 | -0.002 | -0.001 |
| baseline_w_0.4_0.4_0.2 | +0.23 | +0.27 | +0.03 | +0.00 | +0.05 | +0.04 | +0.01 | +0.31 | -0.13 | +1.33 | +5.86 | -0.001 | -0.000 |

Lower MAE is better. The default configuration is the one shipped in `BaselineConfig`; if a grid variant is clearly better on real data, update the default and record the change in DECISIONS.md.
