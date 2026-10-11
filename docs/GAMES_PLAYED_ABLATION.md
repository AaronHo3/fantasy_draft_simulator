# Games played: help or harm?

Question: does projecting games played (availability) and multiplying it into season value make the
draft ranking better or worse? Tested 2026-10-10 on two holdout seasons with the learned models.
Ranking metric: Spearman correlation between projected and realized fantasy value (players with
≥ 20 GP). Draft metric: paired mock drafts, my seat on the variant, the 11 opponents on the old
baseline; Δ = categories won per matchup versus the same seat drafting on the old baseline
(`docs/EVALUATION_gp_*.md`, `docs/EVALUATION_model_vs_model_*.md`).

## Ranking quality (Spearman, ridge model)

| games-played source | 2024-25 | 2025-26 |
|---|---|---|
| model projection (shrunk, MAE ≈ 12.5–13 games) | 0.754 | 0.660 |
| half model / half 70 | 0.747 | 0.661 |
| flat 70 for everyone | 0.734 | 0.652 |
| three-year average | 0.734 | 0.625 |
| last season as-is | 0.713 | 0.633 |

## Draft edge (Δ categories won per matchup, ± SE ≈ 0.10, 120 paired drafts per cell)

| games-played source | 2024-25 | 2025-26 |
|---|---|---|
| model projection | −0.07 | +1.07 |
| flat 70 | −0.64 | +1.40 |
| last season as-is | −0.14 | −0.48 |

## Reading

- Using **raw history** for availability is harmful on both metrics in both years: last season's
  games played is the worst source. Injuries do not repeat cleanly, and penalizing a star for one
  lost season costs more than it saves.
- Using the **model's projection** (which regresses heavily toward the league norm) is the best
  single choice for ranking quality in both years.
- In the drafts the signal is noisier: ignoring availability entirely was better in 2025-26 and
  much worse in 2024-25. The expected value favors the model projection, and its downside year is
  flat rather than a loss.

Decision (DEC-20): keep the model's games-played projection in the season value, and never use
last season's games played directly. A shrunk version (half model, half 70) is a conservative
alternative with the same ranking quality.
