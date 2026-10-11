import numpy as np
import pandas as pd
import pytest

from app.projections.baseline import BaselineConfig, evaluate_projection, naive_last_season, project_baseline

SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]


def synth_totals(n=120, seed=0, rate_noise=0.0, age_range=(20, 34)):
    rng = np.random.default_rng(seed)
    rows = []
    for pid in range(n):
        mpg = rng.uniform(12, 36)
        gp0 = int(rng.integers(40, 82))
        rates = {
            "reb": rng.uniform(0.08, 0.35),
            "ast": rng.uniform(0.05, 0.3),
            "stl": rng.uniform(0.01, 0.06),
            "blk": rng.uniform(0.005, 0.07),
            "tov": rng.uniform(0.03, 0.12),
            "fga": rng.uniform(0.25, 0.6),
            "fg3a": rng.uniform(0.0, 0.25),
            "fta": rng.uniform(0.05, 0.25),
        }
        fgp, ftp, f3p = rng.uniform(0.42, 0.6), rng.uniform(0.6, 0.9), rng.uniform(0.3, 0.42)
        age = rng.uniform(*age_range)
        for s_i, season in enumerate(SEASONS):
            if pid % 10 == 0 and s_i < 3:
                continue  # some players have one season of history only
            gp = int(np.clip(gp0 + rng.integers(-15, 15), 10, 82))
            mins = mpg * gp * rng.uniform(0.9, 1.1)
            yr = {k: v * float(np.exp(rng.normal(0, rate_noise))) for k, v in rates.items()}
            fga = yr["fga"] * mins
            fg3a = min(yr["fg3a"] * mins, fga)
            fta = yr["fta"] * mins
            fgm, fg3m, ftm = fga * fgp, min(fg3a * f3p, fga * fgp), fta * ftp
            rows.append(
                {
                    "nba_id": pid,
                    "name": f"P{pid}",
                    "season": season,
                    "season_type": "Regular Season",
                    "team": "AAA" if pid % 7 else ("BBB" if s_i % 2 else "AAA"),
                    "team_count": 1,
                    "age": age - (3 - s_i),
                    "gp": gp,
                    "min": mins,
                    "fgm": round(fgm),
                    "fga": round(fga),
                    "fg3m": round(fg3m),
                    "fg3a": round(fg3a),
                    "ftm": round(ftm),
                    "fta": round(fta),
                    "oreb": 0,
                    "dreb": 0,
                    "reb": round(yr["reb"] * mins),
                    "ast": round(yr["ast"] * mins),
                    "tov": round(yr["tov"] * mins),
                    "stl": round(yr["stl"] * mins),
                    "blk": round(yr["blk"] * mins),
                    "pts": round(2 * fgm + fg3m + ftm),
                }
            )
    return pd.DataFrame(rows)


def test_baseline_is_coherent_and_uses_only_prior_seasons():
    tot = synth_totals()
    res = project_baseline(tot, "2026-27")
    t = res.table
    assert len(t) > 100 and t["method"].eq("baseline-v1").all()
    assert (t["pg_FG3M"] <= t["pg_FGM"] + 1e-9).all() and (t["pg_FG3A"] <= t["pg_FGA"] + 1e-9).all()
    assert (t["pg_FTM"] <= t["pg_FTA"] + 1e-9).all()
    assert np.allclose(t["pg_PTS"], 2 * t["pg_FGM"] + t["pg_FG3M"] + t["pg_FTM"])
    assert (t["pg_GP"] <= 82).all() and (t["pg_MIN"] <= 38).all()
    assert (t["sd_PTS"] > 0).all()
    # a player with a single season of history gets more shrinkage (closer to prior) and larger cv
    stable = t[(~t["team_changed"]) & (t["age"] < 32)]
    one = stable[stable["n_seasons"] == 1].iloc[0]
    many = stable[stable["n_seasons"] == 3].iloc[0]
    assert one["sd_REB"] / one["pg_REB"] > many["sd_REB"] / many["pg_REB"]
    # projecting 2025-26 must not use 2025-26 rows
    res2 = project_baseline(tot, "2025-26")
    assert res2.table["n_seasons"].max() == 3  # 2022-23..2024-25 only


def test_baseline_beats_or_matches_naive_on_synthetic_holdout():
    tot = synth_totals(n=200, seed=3, rate_noise=0.15, age_range=(25, 29))
    pred = project_baseline(tot, "2025-26").table
    naive = naive_last_season(tot, "2025-26")
    e_b = evaluate_projection(pred, tot, "2025-26")
    e_n = evaluate_projection(naive, tot, "2025-26")
    assert e_b["_n"]["players"] > 100
    # with year-to-year rate noise, the recency-weighted shrunk estimate should beat last season alone
    assert e_b["PTS"]["mae"] < e_n["PTS"]["mae"]
    assert e_b["REB"]["mae"] < e_n["REB"]["mae"]
    assert "FG_PCT" in e_b and "GP" in e_b


def test_positions_select_group_prior():
    tot = synth_totals()
    pos = pd.Series({i: ("C" if i % 2 else "PG") for i in range(120)})
    res = project_baseline(tot, "2026-27", positions=pos)
    assert set(res.priors) >= {"ALL", "C", "PG"}


def test_insufficient_history_raises():
    tot = synth_totals().head(3)
    with pytest.raises(ValueError):
        project_baseline(tot, "2026-27", cfg=BaselineConfig())
