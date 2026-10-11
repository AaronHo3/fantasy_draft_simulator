"""Projection research: score model variants on two holdout seasons by forecast error and ranking quality.

Ranking quality is what the draft needs: Spearman correlation between projected and realized fantasy
value (unweighted z-sum over the nine categories, standardized on realized season totals) among players
with >= 20 GP, plus the overlap of the projected top 150 with the realized top 150.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from app.engine.categories import PRIM_IDX, PRIMITIVES, select_pool, standardize
from app.league.config import DEFAULT_NINE_CATEGORIES
from app.projections.baseline import BaselineConfig, evaluate_projection, naive_last_season, project_baseline
from app.projections.learned import blend_tables, fit_ridge, normalize_games, project_learned, with_games
from app.settings import REPO_DIR

CATS = DEFAULT_NINE_CATEGORIES
COLS = {"GP": "gp", "MIN": "min", "PTS": "pts", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk", "FG3M": "fg3m",
        "FG3A": "fg3a", "FGM": "fgm", "FGA": "fga", "FTM": "ftm", "FTA": "fta", "TOV": "tov"}


def load_tables(data_dir: Path):
    nd = Path(data_dir) / "nba" / "normalized"
    tot = pd.read_parquet(nd / "season_totals.parquet")
    logs = pd.read_parquet(nd / "game_logs.parquet")
    tot = normalize_games(tot, logs)
    espn = pd.read_parquet(nd / "espn_players.parquet").set_index("espn_id")
    cw = pd.read_parquet(nd / "crosswalk.parquet")
    pos = pd.Series({int(r.nba_id): espn.loc[int(r.espn_id), "primary_position"] for r in cw.itertuples()
                     if pd.notna(r.nba_id) and pd.notna(r.espn_id) and isinstance(espn.loc[int(r.espn_id), "primary_position"], str)})
    return tot, logs, pos


def fit_age_table(tot: pd.DataFrame, before: str) -> dict[int, float]:
    """Median year-over-year change in per-minute fantasy production by age, from seasons before ``before``."""
    df = tot[(tot["season"] < before) & (tot["season_type"] == "Regular Season") & (tot["min"] >= 800)].copy()
    df["prod"] = (df["pts"] + 1.2 * df["reb"] + 1.5 * df["ast"] + 3 * df["stl"] + 3 * df["blk"] + df["fg3m"] - df["tov"]) / df["min"]
    df = df.sort_values(["nba_id", "season"])
    rows = []
    for _, g in df.groupby("nba_id"):
        for a, b in zip(g.itertuples(), g.iloc[1:].itertuples(), strict=False):
            if int(b.season[:4]) - int(a.season[:4]) == 1:
                rows.append((int(round(a.age)), b.prod / a.prod))
    d = pd.DataFrame(rows, columns=["age", "ratio"])
    med = d.groupby("age")["ratio"].median()
    cnt = d.groupby("age").size()
    table = {}
    for age in range(19, 40):
        if age in med.index and cnt[age] >= 15:
            table[age] = float(np.clip(med[age], 0.9, 1.1))
        else:
            table[age] = 1.0
    return table


def _value_matrix(df: pd.DataFrame) -> np.ndarray:
    m = np.zeros((len(df), len(PRIMITIVES)))
    for k, c in COLS.items():
        m[:, PRIM_IDX[k]] = df[c].to_numpy(dtype=float)
    return m


def ranking_metrics(pred: pd.DataFrame, tot: pd.DataFrame, target: str, min_gp: int = 20) -> dict[str, float]:
    act = tot[(tot["season"] == target) & (tot["season_type"] == "Regular Season")]
    act = act[act["gp"] >= min_gp].set_index("nba_id")
    pred = pred.set_index("nba_id")
    ids = [i for i in pred.index if i in act.index]
    # projected season totals = per-game x projected games; realized = actual totals
    proj = np.zeros((len(ids), len(PRIMITIVES)))
    for j, k in enumerate(PRIMITIVES):
        col = pred.loc[ids, f"pg_{k}"].to_numpy(dtype=float)
        proj[:, j] = col if k in ("MIN", "GP") else col * pred.loc[ids, "pg_GP"].to_numpy(dtype=float)
    real = _value_matrix(act.loc[ids])
    pool = select_pool(real, CATS, 190)
    zr, _ = standardize(real, CATS, pool)
    zp, _ = standardize(proj, CATS, pool)
    vr, vp = zr.sum(axis=1), zp.sum(axis=1)
    rho = float(spearmanr(vp, vr).correlation)
    top_r = set(np.argsort(-vr)[:150])
    top_p = set(np.argsort(-vp)[:150])
    top50_r = set(np.argsort(-vr)[:50])
    top50_p = set(np.argsort(-vp)[:50])
    return {"n": float(len(ids)), "spearman_value": rho, "top150_overlap": len(top_r & top_p) / 150, "top50_overlap": len(top50_r & top50_p) / 50,
            "value_mae": float(np.mean(np.abs(vp - vr)))}


def variants(tot: pd.DataFrame, target: str) -> dict[str, BaselineConfig]:
    base = BaselineConfig()
    age_tab = fit_age_table(tot, target)
    out = {
        "v1_current": base,
        "no_age": replace(base, age_curve="none"),
        "fitted_age": replace(base, age_curve="fitted", age_table=age_tab),
        "4seasons": replace(base, season_weights=(0.5, 0.3, 0.15, 0.05)),
        "5seasons": replace(base, season_weights=(0.45, 0.27, 0.15, 0.09, 0.04)),
        "2seasons": replace(base, season_weights=(0.7, 0.3)),
        "min_trend_0.3": replace(base, minutes_trend_weight=0.3),
        "min_trend_0.5": replace(base, minutes_trend_weight=0.5),
        "games_recency": replace(base, games_weights=(0.6, 0.3, 0.1), k_games=0.5),
        "games_prior_strong": replace(base, k_games=2.0),
        "k_x0.5": replace(base, k_minutes={k: v * 0.5 for k, v in base.k_minutes.items()}, k_attempts={k: v * 0.5 for k, v in base.k_attempts.items()}),
        "k_x2": replace(base, k_minutes={k: v * 2 for k, v in base.k_minutes.items()}, k_attempts={k: v * 2 for k, v in base.k_attempts.items()}),
    }
    return out


def evaluate(data_dir: Path, targets=("2022-23", "2023-24", "2024-25", "2025-26"), extra: dict[str, BaselineConfig] | None = None) -> pd.DataFrame:
    tot, logs, pos = load_tables(data_dir)
    rows = []
    for target in targets:
        vs = variants(tot, target)
        if extra:
            vs.update(extra)
        best_base = replace(BaselineConfig(), season_weights=(0.7, 0.3), minutes_trend_weight=0.3)
        vs["v2_2s_trend"] = best_base
        vs["v2_2s_trend_fittedage"] = replace(best_base, age_curve="fitted", age_table=fit_age_table(tot, target))
        model = fit_ridge(tot, logs, target)
        ridge = project_learned(tot, logs, target, model)
        ridge_rich = project_learned(tot, logs, target, kind="ridge", rich=True)
        gbm_rich = project_learned(tot, logs, target, kind="gbm", rich=True)
        ens_rich = project_learned(tot, logs, target, kind="ens", rich=True)
        base_tab = project_baseline(tot, target, pos, best_base, game_logs=logs).table
        preds: dict[str, pd.DataFrame] = {"naive_last_season": naive_last_season(tot, target), "ridge": ridge,
                                          "ridge_rich": ridge_rich, "gbm_rich": gbm_rich, "ens_rich": ens_rich,
                                          "ridge+v2_blend50": blend_tables(base_tab, ridge, 0.5),
                                          "mix_ridge_ens": blend_tables(ridge, ens_rich, 0.5)}
        for mode in ("flat", "last", "avg3", "shrunk"):
            preds[f"ens_rich_gp_{mode}"] = with_games(ens_rich, mode, tot, target)
            preds[f"ridge_gp_{mode}"] = with_games(ridge, mode, tot, target)
        for name, cfg in vs.items():
            preds[name] = project_baseline(tot, target, pos, cfg, game_logs=logs).table
        for name, pred in preds.items():
            err = evaluate_projection(pred, tot, target)
            rk = ranking_metrics(pred, tot, target)
            rows.append({"target": target, "variant": name, **{f"mae_{k}": err[k]["mae"] for k in ("PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV", "MIN", "GP", "FG_PCT", "FT_PCT")}, **rk,
                         "ridge_lambdas": model.lambdas if name == "ridge" else None, "ridge_n_train": model.n_train if name == "ridge" else None})
    return pd.DataFrame(rows)


def write_report(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or REPO_DIR / "docs" / "PROJECTION_RESEARCH.md"
    L = ["# Projection research", "", f"Generated {datetime.now(UTC).isoformat(timespec='seconds')}. Variants of the baseline scored on two holdout seasons; "
         "fit seasons are everything before the target (2020-21 onward). Ranking metrics use players with >= 20 GP in the target season.", "",
         "Spearman = rank correlation between projected and realized fantasy value (z-sum); top-150 overlap = share of the realized top 150 "
         "that the projection also put in its top 150; value MAE = mean absolute error of the z-sum (units of pool standard deviations).", ""]
    for target, g in df.groupby("target"):
        L += [f"## Target {target}", "", "| variant | Spearman | top-150 | top-50 | value MAE | MIN MAE | GP MAE | PTS | REB | AST | STL | BLK | 3PM | TOV | FG% | FT% |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in g.sort_values("spearman_value", ascending=False).itertuples():
            L.append(f"| {r.variant} | {r.spearman_value:.3f} | {r.top150_overlap:.2f} | {r.top50_overlap:.2f} | {r.value_mae:.2f} | {r.mae_MIN:.2f} | {r.mae_GP:.1f} | "
                     f"{r.mae_PTS:.2f} | {r.mae_REB:.2f} | {r.mae_AST:.2f} | {r.mae_STL:.3f} | {r.mae_BLK:.3f} | {r.mae_FG3M:.2f} | {r.mae_TOV:.2f} | {r.mae_FG_PCT:.4f} | {r.mae_FT_PCT:.4f} |")
        L.append("")
    path.write_text("\n".join(L) + "\n")
    path.with_suffix(".json").write_text(json.dumps(df.to_dict(orient="records"), indent=1))
    return path
