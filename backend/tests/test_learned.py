import numpy as np
import pandas as pd

from app.projections.learned import STATS, blend_tables, build_rows, fit_ridge, project_learned
from tests.test_baseline import synth_totals

SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def synth_logs(tot: pd.DataFrame, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for r in tot.itertuples():
        n = int(min(r.gp, 30))
        mpg = r.min / max(r.gp, 1)
        for i in range(n):
            rows.append({"nba_id": r.nba_id, "season": r.season, "season_type": "Regular Season", "game_date": f"{r.season[:4]}-11-{i + 1:02d}",
                         "min": max(0.0, mpg + rng.normal(0, 3))})
    return pd.DataFrame(rows)


def five_season_totals():
    base = synth_totals(n=150, seed=4, rate_noise=0.12, age_range=(22, 32))
    extra = base[base["season"] == "2022-23"].copy()
    extra["season"] = "2021-22"
    extra["age"] = extra["age"] - 1
    return pd.concat([extra, base], ignore_index=True)


def test_ridge_trains_only_on_prior_transitions_and_is_coherent():
    tot = five_season_totals()
    logs = synth_logs(tot)
    model = fit_ridge(tot, logs, "2025-26")
    assert model.train_seasons == ["2022-23", "2023-24", "2024-25"]  # targets strictly before 2025-26
    assert set(model.coef) == set([*STATS, "mpg", "gp"])
    pred = project_learned(tot, logs, "2025-26", model)
    assert len(pred) > 100 and pred["method"].eq("ridge-v1").all()
    assert (pred["pg_FGM"] <= pred["pg_FGA"] + 1e-9).all()
    assert (pred["pg_FG3M"] <= pred["pg_FGM"] + 1e-9).all() and (pred["pg_FG3M"] <= pred["pg_FG3A"] + 1e-9).all()
    assert (pred["pg_FTM"] <= pred["pg_FTA"] + 1e-9).all()
    assert np.allclose(pred["pg_PTS"], 2 * pred["pg_FGM"] + pred["pg_FG3M"] + pred["pg_FTM"])
    assert pred["pg_GP"].between(5, 82).all() and pred["pg_MIN"].between(0, 38).all()
    assert (pred["sd_PTS"] > 0).all()


def test_features_use_previous_two_seasons_and_trend():
    tot = five_season_totals()
    logs = synth_logs(tot)
    feats = build_rows(tot, logs, "2024-25")
    assert {"pg_pts", "prev_pg_pts", "trend_mpg", "age_next", "team_changed", "has_prev"} <= set(feats.columns)
    assert feats["has_prev"].mean() > 0.5


def test_blend_tables_is_coherent_and_weighted():
    tot = five_season_totals()
    logs = synth_logs(tot)
    a = project_learned(tot, logs, "2025-26")
    b = a.copy()
    b["pg_PTS"] = b["pg_PTS"] * 2
    b["pg_FGM"] = b["pg_FGM"] * 2
    m = blend_tables(a, b, 0.5)
    assert len(m) == len(a)
    assert (m["pg_FGM"] <= m["pg_FGA"] + 1e-9).all()


def test_with_games_modes_and_bounds():
    from app.projections.learned import with_games

    tot = five_season_totals()
    logs = synth_logs(tot)
    base = project_learned(tot, logs, "2025-26")
    flat = with_games(base, "flat", tot, "2025-26")
    assert (flat["pg_GP"] == 70).all()
    last = with_games(base, "last", tot, "2025-26")
    prev = tot[(tot["season"] == "2024-25")].set_index("nba_id")["gp"]
    nid = int(last["nba_id"].iloc[0])
    assert last.loc[last["nba_id"] == nid, "pg_GP"].iloc[0] == float(min(82, max(5, prev.loc[nid])))
    shr = with_games(base, "shrunk", tot, "2025-26")
    assert np.allclose(shr["pg_GP"], 0.5 * base["pg_GP"] + 35)
    assert with_games(base, "model", tot, "2025-26") is base


def test_ensemble_with_rich_features_is_coherent():
    tot = five_season_totals()
    logs = synth_logs(tot)
    pred = project_learned(tot, logs, "2025-26", kind="ens", rich=True)
    assert pred["method"].eq("ens-rich").all() and len(pred) > 100
    assert (pred["pg_FG3M"] <= pred["pg_FGM"] + 1e-9).all() and (pred["pg_FTM"] <= pred["pg_FTA"] + 1e-9).all()
    assert pred["pg_GP"].between(5, 82).all()
