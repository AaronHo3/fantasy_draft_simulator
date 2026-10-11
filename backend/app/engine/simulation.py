"""Correlated weekly matchup simulation and format-specific objectives (vectorized NumPy).

Per player and scenario: games ~ Binomial(games_in_week, availability), a shared lognormal
minutes/usage factor scales every rate, attempts are scaled counts, makes ~ Binomial(attempts, rate),
other counting stats ~ Poisson(games × rate × factor). Points are derived from makes so the
primitives stay coherent. Nothing here is calibrated on real weekly variance yet (MODEL_CARD.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.categories import PRIM_IDX, PRIMITIVES
from app.league.config import CategoryDef, CategoryKind, ScoringFormat, TieRule

USAGE_SIGMA = 0.12
DEFAULT_GAMES_PER_WEEK = 3.5
SEASON_GAMES = 82


@dataclass(frozen=True)
class SimConfig:
    n_scenarios: int = 400
    games_per_week: float = DEFAULT_GAMES_PER_WEEK
    usage_sigma: float = USAGE_SIGMA
    max_starters: int | None = None  # counted-start cap per team-week (weekly lock approximation)


def simulate_players_week(
    rng: np.random.Generator,
    per_game: np.ndarray,
    games: np.ndarray,
    cfg: SimConfig,
    games_per_week: np.ndarray | None = None,
) -> np.ndarray:
    """Weekly totals for each player: shape [n_players, n_scenarios, len(PRIMITIVES)].

    ``games_per_week`` (per player, from the team schedule) overrides the scalar in ``cfg``.
    """
    n, s = per_game.shape[0], cfg.n_scenarios
    avail = np.clip(games / SEASON_GAMES, 0.0, 1.0)
    gpw = np.full(n, cfg.games_per_week) if games_per_week is None else np.asarray(games_per_week, dtype=float)
    g_week = np.floor(gpw).astype(int)[:, None]
    frac = (gpw - np.floor(gpw))[:, None]
    n_games = g_week + (rng.random((n, s)) < frac)
    g = rng.binomial(n_games, avail[:, None])  # [n, s]
    f = np.exp(rng.normal(0.0, cfg.usage_sigma, (n, s)))
    out = np.zeros((n, s, len(PRIMITIVES)))
    scale = g * f  # expected multiplier on per-game rates

    def col(k: str) -> np.ndarray:
        return per_game[:, PRIM_IDX[k]][:, None]

    fga = rng.poisson(np.maximum(col("FGA") * scale, 0.0))
    fg_rate = np.clip(col("FGM") / np.maximum(col("FGA"), 1e-9), 0.0, 1.0)
    fgm = rng.binomial(fga, np.broadcast_to(fg_rate, fga.shape))
    fg3a = np.minimum(rng.poisson(np.maximum(col("FG3A") * scale, 0.0)), fga)
    fg3_rate = np.clip(col("FG3M") / np.maximum(col("FG3A"), 1e-9), 0.0, 1.0)
    fg3m = np.minimum(rng.binomial(fg3a, np.broadcast_to(fg3_rate, fg3a.shape)), fgm)
    fta = rng.poisson(np.maximum(col("FTA") * scale, 0.0))
    ft_rate = np.clip(col("FTM") / np.maximum(col("FTA"), 1e-9), 0.0, 1.0)
    ftm = rng.binomial(fta, np.broadcast_to(ft_rate, fta.shape))
    out[:, :, PRIM_IDX["FGA"]] = fga
    out[:, :, PRIM_IDX["FGM"]] = fgm
    out[:, :, PRIM_IDX["FG3A"]] = fg3a
    out[:, :, PRIM_IDX["FG3M"]] = fg3m
    out[:, :, PRIM_IDX["FTA"]] = fta
    out[:, :, PRIM_IDX["FTM"]] = ftm
    out[:, :, PRIM_IDX["PTS"]] = 2 * fgm + fg3m + ftm
    for k in ("REB", "AST", "STL", "BLK", "TOV"):
        out[:, :, PRIM_IDX[k]] = rng.poisson(np.maximum(col(k) * scale, 0.0))
    out[:, :, PRIM_IDX["MIN"]] = col("MIN") * scale
    out[:, :, PRIM_IDX["GP"]] = g
    return out


def team_totals(
    player_week: np.ndarray, roster_idx: list[int], max_starters: int | None = None, weights: np.ndarray | None = None
) -> np.ndarray:
    """Sum a roster's simulated weeks: [n_scenarios, P].

    Weekly lock: with ``max_starters`` the roster's top players by projected minutes are counted.
    Daily lineups: ``weights`` (per roster player, 0..1) scale each player's week by the expected
    share of their games that fit the daily slots (see schedule_model.daily_counted_fraction).
    """
    if not roster_idx:
        return np.zeros((player_week.shape[1], player_week.shape[2]))
    idx = list(roster_idx)
    if weights is not None:
        w = np.asarray(weights, dtype=float)
        return (player_week[idx] * w[:, None, None]).sum(axis=0)
    if max_starters is not None and len(idx) > max_starters:
        mins = player_week[idx, :, PRIM_IDX["MIN"]].mean(axis=1)
        keep = np.argsort(-mins)[:max_starters]
        idx = [idx[k] for k in keep]
    return player_week[idx].sum(axis=0)


def category_outcomes(a: np.ndarray, b: np.ndarray, categories: list[CategoryDef], tie_rule: TieRule) -> np.ndarray:
    """Per-scenario per-category outcome for A vs B: +1 win, 0 tie, -1 loss. Shape [S, C]."""
    s = a.shape[0]
    out = np.zeros((s, len(categories)))
    for j, c in enumerate(categories):
        if c.kind == CategoryKind.ratio:
            na, da = a[:, PRIM_IDX[c.numerator]], a[:, PRIM_IDX[c.denominator]]
            nb, db = b[:, PRIM_IDX[c.numerator]], b[:, PRIM_IDX[c.denominator]]
            va = np.where(da > 0, na / np.maximum(da, 1e-9), np.nan)
            vb = np.where(db > 0, nb / np.maximum(db, 1e-9), np.nan)
            unknown = np.isnan(va) | np.isnan(vb)
            diff = np.where(unknown, 0.0, va - vb)
            if tie_rule.zero_attempts == "loss":
                diff = np.where(np.isnan(va) & ~np.isnan(vb), -1.0, diff)
                diff = np.where(np.isnan(vb) & ~np.isnan(va), 1.0, diff)
        else:
            diff = a[:, PRIM_IDX[c.key]] - b[:, PRIM_IDX[c.key]]
        sign = np.sign(diff)
        out[:, j] = sign if c.higher_is_better else -sign
    return out


def objective(outcomes: np.ndarray, fmt: ScoringFormat, tie_rule: TieRule) -> np.ndarray:
    """Per-scenario objective for team A. each: categories won (+tie credit); most: 1/0.5/0."""
    wins = (outcomes == 1).sum(axis=1)
    ties = (outcomes == 0).sum(axis=1)
    losses = (outcomes == -1).sum(axis=1)
    if fmt == ScoringFormat.h2h_each_category:
        return wins + tie_rule.each_category_tie_value * ties
    if fmt == ScoringFormat.h2h_most_categories:
        return np.where(wins > losses, 1.0, np.where(wins == losses, 0.5, 0.0))
    raise ValueError("roto uses roto_objective")


def roto_objective(all_team_totals: np.ndarray, categories: list[CategoryDef]) -> np.ndarray:
    """Expected roto points per team from simulated season-scale totals: [S, T] -> [T]."""
    s, t, _ = all_team_totals.shape
    pts = np.zeros((s, t))
    for _j, c in enumerate(categories):
        if c.kind == CategoryKind.ratio:
            num = all_team_totals[:, :, PRIM_IDX[c.numerator]]
            den = all_team_totals[:, :, PRIM_IDX[c.denominator]]
            v = np.where(den > 0, num / np.maximum(den, 1e-9), -np.inf)
        else:
            v = all_team_totals[:, :, PRIM_IDX[c.key]]
        v = v if c.higher_is_better else -v
        # rank points: best gets T; ties share average via double argsort on (value) with mean of equals
        order = np.argsort(np.argsort(v, axis=1, kind="stable"), axis=1) + 1  # 1..T ascending
        pts += order.astype(float)
    return pts.mean(axis=0)


def category_win_probabilities(outcomes: np.ndarray) -> np.ndarray:
    return (outcomes == 1).mean(axis=0) + 0.5 * (outcomes == 0).mean(axis=0)
