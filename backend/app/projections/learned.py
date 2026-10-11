"""Learned projection: ridge regression per stat on year-to-year transitions (transparent, no leakage).

For each player-season t the features are last season's per-game and per-minute numbers, the season
before, minutes trend over the last 25 games, games played history, age and a team-change flag; the
targets are next season's per-game stats, minutes and games. Training uses only transitions whose
target season precedes the projection target. Ridge is solved in closed form; the penalty is chosen on
the most recent training transition. Outputs are made coherent (FGM <= FGA, 3PM <= min(3PA, FGM),
FTM <= FTA, PTS = 2*FGM + 3PM + FTM).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.engine.categories import PRIM_IDX, PRIMITIVES
from app.projections.baseline import recent_minutes

STATS = ["pts", "reb", "ast", "stl", "blk", "fg3m", "fg3a", "fgm", "fga", "ftm", "fta", "tov"]
TARGETS = [*STATS, "mpg", "gp"]
LAMBDAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
MIN_GP_TRAIN = 10


def normalize_games(tot: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    """Scale games played to an 82-game pace using each season's median team schedule length
    (2019-20 and 2020-21 were shortened). Totals and minutes are left as they are; per-game rates are unaffected."""
    rs = logs[logs["season_type"] == "Regular Season"]
    length = rs.groupby(["season", "team"])["game_id"].nunique().groupby("season").median()
    out = tot.copy()
    factor = out["season"].map(lambda s: 82.0 / float(length.get(s, 82.0)))
    out["gp"] = (out["gp"] * factor).clip(upper=82.0)
    return out


def _season_after(season: str) -> str:
    y = int(season[:4]) + 1
    return f"{y}-{str(y + 1)[-2:]}"


def _season_before(season: str) -> str:
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[-2:]}"


def role_features(logs: pd.DataFrame, season: str) -> pd.DataFrame:
    """Per player: share of games with >= 28 / >= 20 minutes, last-10-game minutes, playoff minutes per game."""
    g = logs[(logs["season"] == season) & (logs["season_type"] == "Regular Season")].sort_values(["nba_id", "game_date"])
    grp = g.groupby("nba_id")["min"]
    out = pd.DataFrame({"share28": grp.apply(lambda x: float((x >= 28).mean())), "share20": grp.apply(lambda x: float((x >= 20).mean())),
                        "last10_mpg": g.groupby("nba_id").tail(10).groupby("nba_id")["min"].mean()})
    po = logs[(logs["season"] == season) & (logs["season_type"] == "Playoffs")].groupby("nba_id")["min"].agg(["mean", "size"])
    out["po_mpg"] = po["mean"].reindex(out.index).fillna(0.0)
    out["po_games"] = po["size"].reindex(out.index).fillna(0.0)
    return out


def build_rows(tot: pd.DataFrame, logs: pd.DataFrame, feature_season: str, rich: bool = True) -> pd.DataFrame:
    """One row per player with a ``feature_season`` line (regular season), features only."""
    rs = tot[tot["season_type"] == "Regular Season"]
    cur = rs[rs["season"] == feature_season].set_index("nba_id")
    prev = rs[rs["season"] == _season_before(feature_season)].set_index("nba_id")
    prev2 = rs[rs["season"] == _season_before(_season_before(feature_season))].set_index("nba_id")
    trend = recent_minutes(logs, feature_season, 25)
    role = role_features(logs, feature_season) if rich else None
    rows = []
    for nid, r in cur.iterrows():
        gp = max(float(r["gp"]), 1.0)
        mins = max(float(r["min"]), 1.0)
        f: dict[str, float] = {"nba_id": int(nid)}
        for s in STATS:
            f[f"pg_{s}"] = float(r[s]) / gp
            f[f"pm_{s}"] = float(r[s]) / mins * 36.0
        f["mpg"] = mins / gp
        f["gp"] = float(r["gp"])
        f["trend_mpg"] = float(trend.loc[nid]) if nid in trend.index else f["mpg"]
        f["age_next"] = float(r["age"]) + 1.0
        f["age_sq"] = f["age_next"] ** 2
        f["young"] = max(0.0, 24.0 - f["age_next"])
        f["old"] = max(0.0, f["age_next"] - 30.0)
        if nid in prev.index:
            p = prev.loc[nid]
            pgp = max(float(p["gp"]), 1.0)
            pmins = max(float(p["min"]), 1.0)
            for s in STATS:
                f[f"prev_pg_{s}"] = float(p[s]) / pgp
            f["prev_mpg"] = pmins / pgp
            f["prev_gp"] = float(p["gp"])
            f["has_prev"] = 1.0
            f["team_changed"] = float(str(p["team"]) != str(r["team"]))
        else:
            for s in STATS:
                f[f"prev_pg_{s}"] = f[f"pg_{s}"]
            f["prev_mpg"] = f["mpg"]
            f["prev_gp"] = f["gp"]
            f["has_prev"] = 0.0
            f["team_changed"] = 0.0
        f["log_min"] = np.log1p(mins)
        if rich:
            f["missed"] = 82.0 - float(r["gp"])
            f["prev_missed"] = 82.0 - f["prev_gp"]
            f["gp2"] = float(prev2.loc[nid, "gp"]) if nid in prev2.index else f["prev_gp"]
            f["has_prev2"] = float(nid in prev2.index)
            if role is not None and nid in role.index:
                for c in ("share28", "share20", "last10_mpg", "po_mpg", "po_games"):
                    f[c] = float(role.loc[nid, c])
            else:
                f["share28"] = float(f["mpg"] >= 28)
                f["share20"] = float(f["mpg"] >= 20)
                f["last10_mpg"] = f["mpg"]
                f["po_mpg"] = 0.0
                f["po_games"] = 0.0
            f["mpg_x_young"] = f["mpg"] * f["young"]
            f["mpg_x_old"] = f["mpg"] * f["old"]
        rows.append(f)
    return pd.DataFrame(rows)


def build_targets(tot: pd.DataFrame, target_season: str) -> pd.DataFrame:
    rs = tot[(tot["season_type"] == "Regular Season") & (tot["season"] == target_season)].set_index("nba_id")
    out = {"nba_id": [], **{t: [] for t in TARGETS}}
    for nid, r in rs.iterrows():
        gp = max(float(r["gp"]), 1.0)
        out["nba_id"].append(int(nid))
        for s in STATS:
            out[s].append(float(r[s]) / gp)
        out["mpg"].append(float(r["min"]) / gp)
        out["gp"].append(float(r["gp"]))
    return pd.DataFrame(out)


@dataclass
class RidgeModel:
    feature_names: list[str]
    mu: np.ndarray
    sigma: np.ndarray
    coef: dict[str, np.ndarray]  # target -> weights (with intercept at index 0)
    lambdas: dict[str, float]
    n_train: int
    train_seasons: list[str]
    kind: str = "ridge"
    rich: bool = False
    gbms: dict[str, object] | None = None  # target -> fitted HistGradientBoostingRegressor (kind gbm / ens)

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        Z = (X[self.feature_names].to_numpy(dtype=float) - self.mu) / self.sigma
        Z1 = np.hstack([np.ones((len(Z), 1)), Z])
        out = {"nba_id": X["nba_id"].to_numpy()}
        for t, w in self.coef.items():
            lin = Z1 @ w
            if self.kind in ("gbm", "ens") and self.gbms is not None:
                gb = self.gbms[t].predict(Z)
                out[t] = gb if self.kind == "gbm" else 0.5 * (lin + gb)
            else:
                out[t] = lin
        return pd.DataFrame(out)


def _ridge(Z1: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    d = Z1.shape[1]
    reg = lam * np.eye(d)
    reg[0, 0] = 0.0
    return np.linalg.solve(Z1.T @ Z1 + reg, Z1.T @ y)


def fit_ridge(tot: pd.DataFrame, logs: pd.DataFrame, target_season: str, min_gp_target: int = MIN_GP_TRAIN,
              kind: str = "ridge", rich: bool = False) -> RidgeModel:
    """Fit on every transition (s -> s+1) with s+1 < target_season. ``kind``: ridge | gbm | ens (average)."""
    seasons = sorted(tot["season"].unique())
    pairs = [(s, _season_after(s)) for s in seasons if _season_after(s) in seasons and _season_after(s) < target_season]
    if len(pairs) < 2:
        raise ValueError("need at least two training transitions")
    frames = []
    for s, s1 in pairs:
        X = build_rows(tot, logs, s, rich)
        Y = build_targets(tot, s1)
        m = X.merge(Y, on="nba_id", suffixes=("", "_y"))
        m = m[m["gp_y"] >= min_gp_target]
        m["pair"] = s1
        frames.append(m)
    data = pd.concat(frames, ignore_index=True)
    feature_names = [c for c in build_rows(tot, logs, pairs[0][0], rich).columns if c != "nba_id"]
    X = data[feature_names].to_numpy(dtype=float)
    mu, sigma = X.mean(axis=0), X.std(axis=0) + 1e-9
    Z1 = np.hstack([np.ones((len(X), 1)), (X - mu) / sigma])
    val_mask = (data["pair"] == pairs[-1][1]).to_numpy()
    coef, lambdas = {}, {}
    for t in TARGETS:
        y = data[f"{t}_y" if f"{t}_y" in data else t].to_numpy(dtype=float)
        best, best_err = None, np.inf
        for lam in LAMBDAS:
            w = _ridge(Z1[~val_mask], y[~val_mask], lam)
            err = float(np.mean(np.abs(Z1[val_mask] @ w - y[val_mask])))
            if err < best_err:
                best, best_err = lam, err
        coef[t] = _ridge(Z1, y, best)
        lambdas[t] = best
    gbms = None
    if kind in ("gbm", "ens"):
        from sklearn.ensemble import HistGradientBoostingRegressor

        gbms = {}
        Zf = Z1[:, 1:]
        for t in TARGETS:
            y = data[f"{t}_y" if f"{t}_y" in data else t].to_numpy(dtype=float)
            gb = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.04, max_iter=400, min_samples_leaf=25,
                                               l2_regularization=1.0, early_stopping=True, validation_fraction=0.15, random_state=7)
            gb.fit(Zf, y)
            gbms[t] = gb
    return RidgeModel(feature_names, mu, sigma, coef, lambdas, int(len(data)), [p[1] for p in pairs], kind, rich, gbms)


def project_learned(tot: pd.DataFrame, logs: pd.DataFrame, target_season: str, model: RidgeModel | None = None,
                    kind: str = "ridge", rich: bool = False) -> pd.DataFrame:
    """Per-game projections for ``target_season`` in the baseline table layout (pg_*/sd_*)."""
    model = model or fit_ridge(tot, logs, target_season, kind=kind, rich=rich)
    X = build_rows(tot, logs, _season_before(target_season), model.rich)
    P = model.predict(X)
    rows = []
    for _, r in P.iterrows():
        pg = np.zeros(len(PRIMITIVES))
        v = {s: max(0.0, float(r[s])) for s in STATS}
        v["fga"] = max(v["fga"], 0.1)
        v["fgm"] = min(v["fgm"], v["fga"])
        v["fg3a"] = min(v["fg3a"], v["fga"])
        v["fg3m"] = min(v["fg3m"], v["fg3a"], v["fgm"])
        v["ftm"] = min(v["ftm"], v["fta"])
        mpg = float(np.clip(r["mpg"], 0.0, 38.0))
        gp = float(np.clip(r["gp"], 5.0, 82.0))
        pg[PRIM_IDX["MIN"]], pg[PRIM_IDX["GP"]] = mpg, gp
        for k, s in (("REB", "reb"), ("AST", "ast"), ("STL", "stl"), ("BLK", "blk"), ("FG3M", "fg3m"), ("FG3A", "fg3a"),
                     ("FGM", "fgm"), ("FGA", "fga"), ("FTM", "ftm"), ("FTA", "fta"), ("TOV", "tov")):
            pg[PRIM_IDX[k]] = v[s]
        pg[PRIM_IDX["PTS"]] = 2 * v["fgm"] + v["fg3m"] + v["ftm"]
        row = {"nba_id": int(r["nba_id"]), "method": f"{model.kind}-{'rich' if model.rich else 'v1'}", "n_seasons": 0, "eff_minutes": 0.0,
               "team_changed": False, "age": None}
        for k in PRIMITIVES:
            row[f"pg_{k}"] = float(pg[PRIM_IDX[k]])
            row[f"sd_{k}"] = float(pg[PRIM_IDX[k]]) * 0.18 if k != "GP" else 12.0
        rows.append(row)
    return pd.DataFrame(rows)


def blend_tables(a: pd.DataFrame, b: pd.DataFrame, w_b: float) -> pd.DataFrame:
    """Per-game blend of two projection tables on shared players (b's weight = w_b); coherence re-applied."""
    m = a.set_index("nba_id").join(b.set_index("nba_id"), how="inner", rsuffix="_b")
    out = []
    for nid, r in m.iterrows():
        row = {"nba_id": int(nid), "method": "blend", "n_seasons": r.get("n_seasons", 0), "eff_minutes": r.get("eff_minutes", 0.0),
               "team_changed": bool(r.get("team_changed", False)), "age": r.get("age")}
        pg = {k: (1 - w_b) * float(r[f"pg_{k}"]) + w_b * float(r[f"pg_{k}_b"]) for k in PRIMITIVES}
        pg["FGM"] = min(pg["FGM"], pg["FGA"])
        pg["FG3A"] = min(pg["FG3A"], pg["FGA"])
        pg["FG3M"] = min(pg["FG3M"], pg["FG3A"], pg["FGM"])
        pg["FTM"] = min(pg["FTM"], pg["FTA"])
        pg["PTS"] = 2 * pg["FGM"] + pg["FG3M"] + pg["FTM"]
        for k in PRIMITIVES:
            row[f"pg_{k}"] = pg[k]
            row[f"sd_{k}"] = (1 - w_b) * float(r[f"sd_{k}"]) + w_b * float(r[f"sd_{k}_b"]) + abs(float(r[f"pg_{k}"]) - float(r[f"pg_{k}_b"])) * 0.5
        out.append(row)
    return pd.DataFrame(out)


def with_games(table: pd.DataFrame, mode: str, tot: pd.DataFrame, target_season: str, flat: float = 70.0) -> pd.DataFrame:
    """Replace the projected games column: model | flat | last | avg3 | shrunk (0.5 model + 0.5 flat)."""
    if mode == "model":
        return table
    rs = tot[tot["season_type"] == "Regular Season"]
    prior = [_season_before(target_season)]
    for _ in range(2):
        prior.append(_season_before(prior[-1]))
    hist = rs[rs["season"].isin(prior)].groupby("nba_id")["gp"]
    last = rs[rs["season"] == prior[0]].set_index("nba_id")["gp"]
    out = table.copy()
    gp = []
    for nid, g in zip(out["nba_id"], out["pg_GP"], strict=True):
        if mode == "flat":
            gp.append(flat)
        elif mode == "last":
            gp.append(float(last.loc[nid]) if nid in last.index else flat)
        elif mode == "avg3":
            gp.append(float(hist.get_group(nid).mean()) if nid in hist.groups else flat)
        elif mode == "shrunk":
            gp.append(0.5 * float(g) + 0.5 * flat)
        else:
            raise ValueError(mode)
    out["pg_GP"] = np.clip(np.array(gp), 5.0, 82.0)
    return out
