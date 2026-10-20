"""Build the real-data snapshot: baseline + ESPN projections, ESPN eligibility/ADP/ranks, rookies' priors."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from app.engine.categories import PRIM_IDX, PRIMITIVES
from app.engine.schedule_model import build_team_schedule
from app.identity.players import Player
from app.projections.baseline import BaselineConfig, project_baseline
from app.projections.snapshot import Snapshot, content_hash, validate_snapshot

ADP_PLACEHOLDER_MIN = 139.0  # ESPN reports ~139.9-140.4 for players without real draft data
# Rookies with no NBA history and only an ESPN projection: ESPN's number is taken at face value by default,
# which ranks some rookies like proven starters. Documented judgment (DEC-23): shrink counting stats and
# minutes, cap games, and widen uncertainty. Not validated (ESPN's past rookie projections are unavailable).
ROOKIE_DISCOUNT = 0.85
ROOKIE_GP_CAP = 65.0
ROOKIE_CV = 0.35
# Players with NBA history who played zero games last season (season-long injury): 22 such returns in
# 2017-2025 produced a median 0.75× of the baseline's projected per-game value, 0.85× minutes and 0.76×
# games (DEC-23). The learned model cannot see them (no feature row), so the baseline/ESPN blend is
# adjusted here and the uncertainty doubled.
# Split by role in the last played season (DEC-23 follow-up): stars (>= 30 mpg, n=7) returned to a median
# 100 % / mean 94 % of projected games and 112 % of projected per-game value; role players (n=15) to 60 %
# of games and 56 % of per-game value (shrunk to 0.75 for the small sample).
STAR_MPG = 30.0
RETURN_GP_FACTOR_STAR = 0.94
RETURN_RATE_FACTOR_STAR = 1.0
RETURN_GP_FACTOR_ROLE = 0.62
RETURN_RATE_FACTOR_ROLE = 0.75
ESPN_ONLY_CV = 0.15
PRIOR_CV = 0.35
PRIOR_GAMES = 60.0
PRIOR_MPG_BY_RANK = ((60, 28.0), (150, 20.0), (10_000, 12.0))
ESPN_PROJ_KEYS = {
    "GP": "proj_gp",
    "MIN": "proj_min",
    "PTS": "proj_pts",
    "REB": "proj_reb",
    "AST": "proj_ast",
    "STL": "proj_stl",
    "BLK": "proj_blk",
    "FG3M": "proj_fg3m",
    "FG3A": "proj_fg3a",
    "FGM": "proj_fgm",
    "FGA": "proj_fga",
    "FTM": "proj_ftm",
    "FTA": "proj_fta",
    "TOV": "proj_tov",
}


def _espn_per_game(row: pd.Series) -> np.ndarray | None:
    gp = row.get("proj_gp")
    if gp is None or not np.isfinite(gp) or gp <= 0:
        return None
    pg = np.zeros(len(PRIMITIVES))
    for k, col in ESPN_PROJ_KEYS.items():
        v = row.get(col)
        v = 0.0 if v is None or not np.isfinite(v) else float(v)
        pg[PRIM_IDX[k]] = gp if k == "GP" else v / gp
    return _coherent(pg)


def _coherent(pg: np.ndarray) -> np.ndarray:
    pg = np.maximum(pg, 0.0)
    pg[PRIM_IDX["FGM"]] = min(pg[PRIM_IDX["FGM"]], pg[PRIM_IDX["FGA"]])
    pg[PRIM_IDX["FTM"]] = min(pg[PRIM_IDX["FTM"]], pg[PRIM_IDX["FTA"]])
    pg[PRIM_IDX["FG3A"]] = min(pg[PRIM_IDX["FG3A"]], pg[PRIM_IDX["FGA"]])
    pg[PRIM_IDX["FG3M"]] = min(pg[PRIM_IDX["FG3M"]], pg[PRIM_IDX["FG3A"]], pg[PRIM_IDX["FGM"]])
    pg[PRIM_IDX["GP"]] = min(pg[PRIM_IDX["GP"]], 82.0)
    return pg


def _prior_per_game(rank: float | None, pos: str | None, priors: dict[str, dict[str, float]]) -> np.ndarray:
    mpg = 10.0
    if rank is not None and np.isfinite(rank):
        for cap, m in PRIOR_MPG_BY_RANK:
            if rank <= cap:
                mpg = m
                break
    pr = priors.get(pos or "ALL", priors["ALL"])
    pg = np.zeros(len(PRIMITIVES))
    pg[PRIM_IDX["MIN"]], pg[PRIM_IDX["GP"]] = mpg, PRIOR_GAMES
    for k in ("REB", "AST", "STL", "BLK", "TOV", "FGA", "FG3A", "FTA"):
        pg[PRIM_IDX[k]] = pr[k] * mpg
    pg[PRIM_IDX["FGM"]] = pg[PRIM_IDX["FGA"]] * pr["FG"]
    pg[PRIM_IDX["FG3M"]] = pg[PRIM_IDX["FG3A"]] * pr["FG3"]
    pg[PRIM_IDX["FTM"]] = pg[PRIM_IDX["FTA"]] * pr["FT"]
    pg[PRIM_IDX["PTS"]] = 2 * pg[PRIM_IDX["FGM"]] + pg[PRIM_IDX["FG3M"]] + pg[PRIM_IDX["FTM"]]
    return _coherent(pg)


def build_real_snapshot(
    data_dir: Path,
    season: str = "2026-27",
    espn_weight: float = 0.5,
    cfg: BaselineConfig | None = None,
    save: bool = True,
    model: str = "ens",
) -> Snapshot:
    """``model``: "ens" (default: ridge + gradient boosting on rich role features, DEC-20), "ridge" (plain),
    or "baseline". Learned models fall back to the baseline for players without a feature season."""
    cfg = cfg or BaselineConfig()
    nd = Path(data_dir) / "nba" / "normalized"
    players = pd.read_parquet(nd / "players.parquet")
    totals = pd.read_parquet(nd / "season_totals.parquet")
    espn = pd.read_parquet(nd / "espn_players.parquet").set_index("espn_id", drop=False)
    cw = pd.read_parquet(nd / "crosswalk.parquet")
    health_src = json.loads((nd / "health.json").read_text()) if (nd / "health.json").exists() else {}
    team_gpw: dict[str, float] = {}
    schedule_label = "generic 3.5 games/week assumption (no schedule loaded)"
    if (nd / "schedule.parquet").exists():
        sched = pd.read_parquet(nd / "schedule.parquet")
        ts = build_team_schedule(sched)
        team_gpw = ts.average_games_per_week()
        schedule_label = (
            f"ESPN schedule {season}: {len(sched)} games, {len(ts.weeks)} Monday-anchored weeks "
            f"({len(ts.full_week_indices())} full); matchup-period boundaries approximated"
        )
    positions = pd.Series(
        {
            int(r.nba_id): espn.loc[int(r.espn_id), "primary_position"]
            for r in cw.itertuples()
            if pd.notna(r.nba_id) and pd.notna(r.espn_id) and pd.notna(espn.loc[int(r.espn_id), "primary_position"])
        }
    )
    logs = pd.read_parquet(nd / "game_logs.parquet") if (nd / "game_logs.parquet").exists() else None
    if logs is not None:
        from app.projections.learned import normalize_games

        totals = normalize_games(totals, logs)
    base = project_baseline(totals, season, positions, cfg, game_logs=logs)
    bl = base.table.set_index("nba_id")
    ridge_info: dict = {}
    if model in ("ridge", "ens") and logs is not None:
        from app.projections.learned import fit_ridge, project_learned

        rm = fit_ridge(totals, logs, season, kind=model, rich=(model == "ens"))
        ridge = project_learned(totals, logs, season, rm).set_index("nba_id")
        ridge_info = {"kind": model, "rich_features": model == "ens", "train_transitions": rm.train_seasons,
                      "n_train": rm.n_train, "lambdas": rm.lambdas, "players": int(len(ridge))}
        # the learned model replaces the baseline where it has a feature season; sd from the baseline when present
        for nid in ridge.index:
            if nid in bl.index:
                for k in PRIMITIVES:
                    bl.loc[nid, f"pg_{k}"] = float(ridge.loc[nid, f"pg_{k}"])
                bl.loc[nid, "method"] = "learned"
            else:
                bl.loc[nid] = ridge.loc[nid]
    nba_active = players.set_index("nba_id")
    latest_age = totals.sort_values("season").groupby("nba_id")["age"].last()
    end_year = int(season[:4]) + 1
    last_season = f"{end_year - 2}-{str(end_year - 1)[-2:]}"
    played_last = set(totals[(totals["season"] == last_season) & (totals["season_type"] == "Regular Season")]["nba_id"].astype(int))
    _rs = totals[totals["season_type"] == "Regular Season"].sort_values("season")
    last_mpg = (_rs.groupby("nba_id").last().assign(mpg=lambda d: d["min"] / d["gp"].clip(lower=1))["mpg"])

    out_players: list[Player] = []
    pg_rows, sd_rows, adps, ranks, sources = [], [], [], [], []
    counts = {"baseline": 0, "espn": 0, "blend": 0, "prior": 0, "missing_eligibility": 0, "no_adp": 0, "ridge": 0}
    for r in cw.itertuples():
        nba_id = int(r.nba_id) if pd.notna(r.nba_id) else None
        espn_id = int(r.espn_id) if pd.notna(r.espn_id) else None
        e = espn.loc[espn_id] if espn_id is not None else None
        if nba_id is not None and nba_id not in nba_active.index and (e is None or pd.isna(e["team"])):
            continue  # not on an NBA roster and not an ESPN roster player
        if nba_id is None and (e is None or pd.isna(e["team"])):
            continue  # ESPN profile without a team: retired / overseas
        team = None
        if nba_id is not None and nba_id in nba_active.index and pd.notna(nba_active.loc[nba_id, "team"]):
            team = str(nba_active.loc[nba_id, "team"])
        elif e is not None and pd.notna(e["team"]):
            team = str(e["team"])
        name = str(e["name"]) if e is not None else str(r.name)
        prim, elig, elig_src, verified = None, frozenset(), "unknown", False
        injury = None
        if e is not None:
            prim = e["primary_position"] if pd.notna(e["primary_position"]) else None
            elig = frozenset(json.loads(e["eligible_positions_json"]))
            if elig:
                elig_src, verified = "espn", True
            injury = e["injury_status"] if pd.notna(e["injury_status"]) else None
        if not elig:
            counts["missing_eligibility"] += 1
        has_hist = nba_id is not None and nba_id in bl.index
        age = None
        if nba_id is not None and nba_id in latest_age.index and pd.notna(latest_age.loc[nba_id]):
            last_season = totals[totals["nba_id"] == nba_id]["season"].max()
            age = float(latest_age.loc[nba_id]) + (end_year - (int(last_season[:4]) + 1))
        from_year = int(nba_active.loc[nba_id, "from_year"]) if nba_id in nba_active.index else None
        rank = float(e["rank_standard"]) if e is not None and pd.notna(e["rank_standard"]) else np.nan
        adp = (
            float(e["adp"])
            if e is not None and pd.notna(e["adp"]) and float(e["adp"]) < ADP_PLACEHOLDER_MIN
            else np.nan
        )
        if np.isnan(adp):
            counts["no_adp"] += 1
        es = _espn_per_game(e) if e is not None else None
        if has_hist:
            row = bl.loc[nba_id]
            b_pg = np.array([row[f"pg_{k}"] for k in PRIMITIVES])
            b_sd = np.array([row[f"sd_{k}"] for k in PRIMITIVES])
            if str(row.get("method", "")) in ("learned", "ridge-v1", "ens-rich"):
                counts["ridge"] += 1
            if es is not None and espn_weight > 0:
                pg = _coherent((1 - espn_weight) * b_pg + espn_weight * es)
                sd = (1 - espn_weight) * b_sd + espn_weight * np.abs(b_pg - es)
                sd[PRIM_IDX["GP"]] = max(b_sd[PRIM_IDX["GP"]], abs(b_pg[PRIM_IDX["GP"]] - es[PRIM_IDX["GP"]]))
                src = "blend"
            else:
                pg, sd, src = b_pg, b_sd, "baseline"
        elif es is not None:
            pg, src = es.copy(), "espn"
            if not has_hist:
                # rookie discount: everything but GP scaled, GP capped, wide uncertainty
                gp_col = PRIM_IDX["GP"]
                gp_val = min(pg[gp_col], ROOKIE_GP_CAP)
                pg = _coherent(pg * ROOKIE_DISCOUNT)
                pg[gp_col] = gp_val
                src = "espn_rookie_discounted"
                counts["rookie_discounted"] = counts.get("rookie_discounted", 0) + 1
            sd = pg * (ROOKIE_CV if src == "espn_rookie_discounted" else ESPN_ONLY_CV)
            sd[PRIM_IDX["GP"]] = 15.0 if src == "espn_rookie_discounted" else 12.0
        else:
            pg, src = _prior_per_game(rank, prim, base.priors), "prior"
            sd = pg * PRIOR_CV
            sd[PRIM_IDX["GP"]] = 15.0
        if has_hist and nba_id not in played_last:
            gp_col = PRIM_IDX["GP"]
            star = float(last_mpg.get(nba_id, 0.0)) >= STAR_MPG
            gp_val = pg[gp_col] * (RETURN_GP_FACTOR_STAR if star else RETURN_GP_FACTOR_ROLE)
            pg = _coherent(pg * (RETURN_RATE_FACTOR_STAR if star else RETURN_RATE_FACTOR_ROLE))
            pg[gp_col] = gp_val
            sd = sd * 2.0
            src = f"{src}_returning"
            counts["returning_from_lost_season"] = counts.get("returning_from_lost_season", 0) + 1
        counts[src] = counts.get(src, 0) + 1
        out_players.append(
            Player(
                player_id=str(r.player_id),
                name=name,
                team=team,
                nba_id=nba_id,
                espn_id=espn_id,
                primary_position=prim,
                eligible_positions=elig,
                eligibility_source=elig_src,
                eligibility_verified=verified,
                injury_status=injury,
                age=None if age is None else round(age, 1),
                years_experience=None if from_year is None else end_year - 1 - from_year,
                is_rookie=not has_hist,
            )
        )
        pg_rows.append(pg)
        sd_rows.append(sd)
        adps.append(adp)
        ranks.append(rank)
        sources.append(src)
    per_game = np.vstack(pg_rows)
    per_game_sd = np.vstack(sd_rows)
    adp_arr, rank_arr = np.array(adps), np.array(ranks)
    created = datetime.now(UTC).isoformat(timespec="seconds")
    adp_asof = str(espn["adp_asof"].dropna().max()) if "adp_asof" in espn else None
    snap = Snapshot(
        snapshot_id="nba-" + content_hash(per_game, adp_arr),
        label=f"NBA {season}: {('learned (' + model + ')') if ridge_info else 'baseline'} + ESPN projections (blend {espn_weight:.2f}), built {created[:10]}",
        source="nba",
        season=season,
        created_at=created,
        players=tuple(out_players),
        per_game=per_game,
        per_game_sd=per_game_sd,
        adp=adp_arr,
        rank=rank_arr,
        projection_source=tuple(sources),
        adp_platform="espn",
        adp_asof=adp_asof,
        rank_source="espn_standard",
        provenance={
            "baseline_config": cfg.__dict__ | {"k_minutes": cfg.k_minutes, "k_attempts": cfg.k_attempts},
            "espn_weight": espn_weight,
            "sources": health_src.get("sources", {}),
            "snapshot_date": health_src.get("snapshot_date"),
            "adp_placeholder_min": ADP_PLACEHOLDER_MIN,
            "universe_rule": "NBA active roster players + ESPN active players with a team",
        },
        health={
            "players": len(out_players),
            "with_adp": int(np.isfinite(adp_arr).sum()),
            "with_rank": int(np.isfinite(rank_arr).sum()),
            "projection_sources": counts,
            "unresolved_identities": health_src.get("coverage", {}).get("unresolved_identities"),
            "missing_eligibility": counts["missing_eligibility"],
            "sources": health_src.get("sources", {}),
        },
        is_demo=False,
        team_games_per_week=team_gpw,
        schedule_label=schedule_label,
    )
    problems = validate_snapshot(snap)
    if problems:
        raise ValueError(f"snapshot failed validation: {problems}")
    if save:
        snap.save(Path(data_dir) / "nba" / "snapshots" / snap.snapshot_id)
    return snap
