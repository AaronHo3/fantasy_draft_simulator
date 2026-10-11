"""Transparent baseline projection from NBA season totals (per-minute rates, shrinkage, minutes, games).

Input: normalized ``season_totals`` rows (one aggregate row per player-season, regular season only)
with columns nba_id, season, age, gp, min, fgm, fga, fg3m, fg3a, ftm, fta, reb, ast, tov, stl, blk, pts.
Output: per-game projections for PRIMITIVES plus per-game sd, one row per player with history.
All constants live in ``BaselineConfig`` and are documented in docs/MODEL_CARD.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.engine.categories import PRIM_IDX, PRIMITIVES

COUNTING = ("REB", "AST", "STL", "BLK", "TOV", "FGA", "FG3A", "FTA")
STAT_COLS = {
    "REB": "reb",
    "AST": "ast",
    "STL": "stl",
    "BLK": "blk",
    "TOV": "tov",
    "FGA": "fga",
    "FG3A": "fg3a",
    "FTA": "fta",
    "FGM": "fgm",
    "FG3M": "fg3m",
    "FTM": "ftm",
    "PTS": "pts",
}


@dataclass(frozen=True)
class BaselineConfig:
    # Validated on the 2025-26 holdout (docs/VALIDATION.md, DEC-15): weaker shrinkage and more recency than
    # the initial guess. The third-season weight could not be validated (only two fit seasons available).
    season_weights: tuple[float, ...] = (0.6, 0.3, 0.1)  # t-1, t-2, t-3
    k_minutes: dict[str, float] = field(
        default_factory=lambda: {
            "REB": 140,
            "AST": 140,
            "TOV": 140,
            "FGA": 105,
            "FG3A": 140,
            "FTA": 140,
            "STL": 280,
            "BLK": 280,
        }
    )
    k_attempts: dict[str, float] = field(default_factory=lambda: {"FG": 105, "FT": 52, "FG3": 70})
    k_games_mpg: float = 15.0  # games-equivalent shrinkage for minutes per game
    prior_games: float = 68.0
    k_games: float = 1.0  # season-equivalents of shrinkage toward prior games
    mpg_cap: float = 38.0
    min_history_minutes: float = 100.0
    base_cv: float = 0.10
    team_change_cv: float = 0.05
    age_cv_threshold: float = 32.0
    age_cv: float = 0.04
    games_sd: float = 10.0
    prior_min_minutes: float = 500.0  # players counted in position-group priors
    # v2 options (validated in docs/VALIDATION.md; see research.py)
    minutes_trend_weight: float = 0.0  # weight on last-N-games minutes of the most recent season (needs game logs)
    minutes_trend_games: int = 25
    games_weights: tuple[float, ...] | None = None  # recency weights for games played; None = season_weights
    age_curve: str = "fixed"  # fixed | none | fitted
    age_table: dict[int, float] | None = None  # fitted multiplicative year-over-year change by age


@dataclass(frozen=True)
class BaselineResult:
    table: pd.DataFrame  # nba_id, pg_<PRIM>, sd_<PRIM>, n_seasons, eff_minutes, team_changed, age, method
    priors: dict[str, dict[str, float]]  # position group -> per-minute prior rates and shooting rates


def _season_end_year(season: str) -> int:
    return int(season[:4]) + 1


def _age_multiplier(age: float | None, cfg: BaselineConfig | None = None) -> float:
    if age is None or np.isnan(age):
        return 1.0
    mode = cfg.age_curve if cfg else "fixed"
    if mode == "none":
        return 1.0
    if mode == "fitted" and cfg and cfg.age_table:
        a = int(round(age))
        keys = sorted(cfg.age_table)
        a = min(max(a, keys[0]), keys[-1])
        return float(cfg.age_table.get(a, 1.0))
    if age < 24:
        return 1.0 + 0.015 * (24 - age)
    if age > 30:
        return 1.0 - 0.012 * (age - 30)
    return 1.0


def _minutes_age_multiplier(age: float | None) -> float:
    if age is None or np.isnan(age) or age <= 33:
        return 1.0
    return max(0.7, 1.0 - 0.02 * (age - 33))


def position_group_priors(
    latest: pd.DataFrame, positions: pd.Series, cfg: BaselineConfig
) -> dict[str, dict[str, float]]:
    """Per-minute rates and shooting rates by position group from last season's rotation players.

    ``positions`` maps nba_id -> primary position (PG/SG/SF/PF/C) or NaN. Group 'ALL' is the fallback.
    """
    df = latest[latest["min"] >= cfg.prior_min_minutes].copy()
    df["pos"] = df["nba_id"].map(positions).fillna("ALL")
    out: dict[str, dict[str, float]] = {}
    groups = {"ALL": df, **{g: sub for g, sub in df.groupby("pos") if g != "ALL"}}
    for g, sub in groups.items():
        if len(sub) < 8:
            continue
        mins = sub["min"].sum()
        d = {k: float(sub[STAT_COLS[k]].sum() / mins) for k in COUNTING}
        d["FG"] = float(sub["fgm"].sum() / max(sub["fga"].sum(), 1))
        d["FT"] = float(sub["ftm"].sum() / max(sub["fta"].sum(), 1))
        d["FG3"] = float(sub["fg3m"].sum() / max(sub["fg3a"].sum(), 1))
        d["MPG"] = float((sub["min"] / sub["gp"]).median())
        out[g] = d
    return out


def recent_minutes(game_logs: pd.DataFrame, season: str, n_games: int) -> pd.Series:
    """Minutes per game over each player's last ``n_games`` of ``season`` (regular season)."""
    g = game_logs[(game_logs["season"] == season) & (game_logs["season_type"] == "Regular Season")]
    g = g.sort_values(["nba_id", "game_date"])
    tail = g.groupby("nba_id").tail(n_games)
    return tail.groupby("nba_id")["min"].mean()


def project_baseline(
    season_totals: pd.DataFrame,
    target_season: str,
    positions: pd.Series | None = None,
    cfg: BaselineConfig | None = None,
    season_type: str = "Regular Season",
    game_logs: pd.DataFrame | None = None,
) -> BaselineResult:
    """Project per-game stats for ``target_season`` from the preceding regular seasons (as many as weights)."""
    cfg = cfg or BaselineConfig()
    df = season_totals[season_totals["season_type"] == season_type].copy()
    end = _season_end_year(target_season)
    prior_seasons = [f"{end - 1 - k - 1}-{str(end - 1 - k)[-2:]}" for k in range(len(cfg.season_weights))]
    weights = dict(zip(prior_seasons, cfg.season_weights, strict=True))
    df = df[df["season"].isin(prior_seasons)].copy()
    df["w"] = df["season"].map(weights)
    positions = positions if positions is not None else pd.Series(dtype=object)
    latest = df[df["season"] == prior_seasons[0]]
    priors = position_group_priors(latest, positions, cfg)
    if "ALL" not in priors:
        raise ValueError("not enough history to build priors")
    trend = recent_minutes(game_logs, prior_seasons[0], cfg.minutes_trend_games) if (game_logs is not None and cfg.minutes_trend_weight > 0) else None
    gw = dict(zip(prior_seasons, cfg.games_weights, strict=False)) if cfg.games_weights else None
    rows = []
    for nba_id, g in df.groupby("nba_id"):
        g = g.sort_values("season", ascending=False)
        w = g["w"].to_numpy()
        mins = g["min"].to_numpy(dtype=float)
        gp = g["gp"].to_numpy(dtype=float)
        if mins.sum() < cfg.min_history_minutes:
            continue
        pos = positions.get(nba_id) if len(positions) else None
        prior = priors.get(pos if isinstance(pos, str) else "ALL", priors["ALL"])
        wmin = float((w * mins).sum())  # effective weighted minutes
        age = float(g.iloc[0]["age"]) + (end - _season_end_year(g.iloc[0]["season"])) if "age" in g else np.nan
        team_changed = bool(len(set(g["team"].astype(str))) > 1) if "team" in g else False
        rates: dict[str, float] = {}
        for k in COUNTING:
            num = float((w * g[STAT_COLS[k]].to_numpy(dtype=float)).sum())
            raw = num / max(wmin, 1e-9)
            kk = cfg.k_minutes[k]
            rates[k] = (wmin * raw + kk * prior[k]) / (wmin + kk)

        fg_pct = _shrunk_rate(g, w, "fgm", "fga", cfg.k_attempts["FG"], prior["FG"])
        ft_pct = _shrunk_rate(g, w, "ftm", "fta", cfg.k_attempts["FT"], prior["FT"])
        fg3_pct = _shrunk_rate(g, w, "fg3m", "fg3a", cfg.k_attempts["FG3"], prior["FG3"])
        # minutes per game, shrunk toward the group median by games-equivalent
        mpg_hist = float((w * mins).sum() / max((w * gp).sum(), 1e-9))
        n_g = float((w * gp).sum())
        mpg = (n_g * mpg_hist + cfg.k_games_mpg * prior["MPG"]) / (n_g + cfg.k_games_mpg)
        if trend is not None and nba_id in trend.index and g.iloc[0]["season"] == prior_seasons[0]:
            mpg = (1 - cfg.minutes_trend_weight) * mpg + cfg.minutes_trend_weight * float(trend.loc[nba_id])
        mpg = min(cfg.mpg_cap, mpg * _minutes_age_multiplier(age))
        wg = np.array([gw.get(sn, 0.0) for sn in g["season"]]) if gw is not None else w
        games = (float((wg * gp).sum()) + cfg.k_games * cfg.prior_games) / (float(wg.sum()) + cfg.k_games)
        games = float(np.clip(games, 5, 82))
        mult = _age_multiplier(age, cfg)
        pg = np.zeros(len(PRIMITIVES))
        pg[PRIM_IDX["MIN"]] = mpg
        pg[PRIM_IDX["GP"]] = games
        for k in ("REB", "AST", "STL", "BLK", "TOV"):
            pg[PRIM_IDX[k]] = rates[k] * mpg * mult
        fga = rates["FGA"] * mpg * mult
        fg3a = min(rates["FG3A"] * mpg * mult, fga)
        fta = rates["FTA"] * mpg * mult
        fgm = fga * fg_pct
        fg3m = min(fg3a * fg3_pct, fgm)
        ftm = fta * ft_pct
        pg[PRIM_IDX["FGA"]], pg[PRIM_IDX["FGM"]] = fga, fgm
        pg[PRIM_IDX["FG3A"]], pg[PRIM_IDX["FG3M"]] = fg3a, fg3m
        pg[PRIM_IDX["FTA"]], pg[PRIM_IDX["FTM"]] = fta, ftm
        pg[PRIM_IDX["PTS"]] = 2 * fgm + fg3m + ftm
        cv = cfg.base_cv * np.sqrt(1.0 / (wmin / 400.0 + 1.0)) + cfg.base_cv
        if team_changed:
            cv += cfg.team_change_cv
        if not np.isnan(age) and age >= cfg.age_cv_threshold:
            cv += cfg.age_cv
        sd = pg * cv
        sd[PRIM_IDX["GP"]] = cfg.games_sd
        sd[PRIM_IDX["MIN"]] = mpg * cv * 0.6
        row = {
            "nba_id": int(nba_id),
            "n_seasons": int(len(g)),
            "eff_minutes": round(wmin, 1),
            "team_changed": team_changed,
            "age": None if np.isnan(age) else round(age, 1),
            "method": "baseline-v1",
        }
        for k in PRIMITIVES:
            row[f"pg_{k}"] = float(pg[PRIM_IDX[k]])
            row[f"sd_{k}"] = float(sd[PRIM_IDX[k]])
        rows.append(row)
    return BaselineResult(pd.DataFrame(rows), priors)


def _shrunk_rate(g: pd.DataFrame, w: np.ndarray, makes: str, att: str, k: float, prior_rate: float) -> float:
    m = float((w * g[makes].to_numpy(dtype=float)).sum())
    a = float((w * g[att].to_numpy(dtype=float)).sum())
    return (m + k * prior_rate) / (a + k)


def naive_last_season(
    season_totals: pd.DataFrame, target_season: str, season_type: str = "Regular Season"
) -> pd.DataFrame:
    """Per-game stats of the immediately preceding season (the comparison baseline for validation)."""
    end = _season_end_year(target_season)
    prev = f"{end - 2}-{str(end - 1)[-2:]}"
    df = season_totals[(season_totals["season"] == prev) & (season_totals["season_type"] == season_type)].copy()
    out = pd.DataFrame({"nba_id": df["nba_id"].astype(int)})
    gp = df["gp"].to_numpy(dtype=float).clip(min=1)
    for k, col in STAT_COLS.items():
        out[f"pg_{k}"] = df[col].to_numpy(dtype=float) / gp
    out["pg_MIN"] = df["min"].to_numpy(dtype=float) / gp
    out["pg_GP"] = gp
    return out


def evaluate_projection(
    pred: pd.DataFrame, actual_totals: pd.DataFrame, season: str, min_gp: int = 20
) -> dict[str, dict[str, float]]:
    """MAE and mean bias of per-game predictions vs. a season's actual per-game stats."""
    act = actual_totals[(actual_totals["season"] == season) & (actual_totals["season_type"] == "Regular Season")]
    act = act[act["gp"] >= min_gp]
    m = pred.merge(act, on="nba_id", how="inner")
    out: dict[str, dict[str, float]] = {"_n": {"players": float(len(m))}}
    gp = m["gp"].to_numpy(dtype=float)
    for k, col in STAT_COLS.items():
        a = m[col].to_numpy(dtype=float) / gp
        p = m[f"pg_{k}"].to_numpy(dtype=float)
        out[k] = {"mae": float(np.mean(np.abs(p - a))), "bias": float(np.mean(p - a))}
    a = m["min"].to_numpy(dtype=float) / gp
    out["MIN"] = {"mae": float(np.mean(np.abs(m["pg_MIN"] - a))), "bias": float(np.mean(m["pg_MIN"] - a))}
    out["GP"] = {"mae": float(np.mean(np.abs(m["pg_GP"] - gp))), "bias": float(np.mean(m["pg_GP"] - gp))}
    fg_p = (m["pg_FGM"] / m["pg_FGA"].clip(lower=1e-9)).to_numpy()
    fg_a = (m["fgm"] / m["fga"].clip(lower=1)).to_numpy()
    out["FG_PCT"] = {
        "mae": float(np.average(np.abs(fg_p - fg_a), weights=m["fga"])),
        "bias": float(np.average(fg_p - fg_a, weights=m["fga"])),
    }
    ft_p = (m["pg_FTM"] / m["pg_FTA"].clip(lower=1e-9)).to_numpy()
    ft_a = (m["ftm"] / m["fta"].clip(lower=1)).to_numpy()
    w = m["fta"].clip(lower=1)
    out["FT_PCT"] = {
        "mae": float(np.average(np.abs(ft_p - ft_a), weights=w)),
        "bias": float(np.average(ft_p - ft_a, weights=w)),
    }
    return out
