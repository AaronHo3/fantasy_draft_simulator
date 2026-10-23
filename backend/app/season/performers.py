"""Team performers: who produced the most for a fantasy team, and who beat their projection by the most.

Source of truth for "actual results" is ESPN's applied box score per matchup period (the stats ESPN
counted for the team that rostered the player that week), stored by sync as ``period_player_stats``.
Contribution is measured on the project's category valuation: the per-game z scale fitted on the
projection pool (``performance._per_game_scale``), so one unit is one category-standard-deviation
per game, and cumulative contribution is per-game value x games counted. The expectation baseline is
the snapshot's per-game projection (learned ensemble blended with ESPN, with the rookie / returning
adjustments) multiplied by the games the player actually played, so availability is not double
counted. Players whose projection is only a prior have no baseline and are shown but not ranked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.draft.events import DraftState
from app.engine.categories import PRIM_IDX, PRIMITIVES, raw_category_matrix
from app.league.config import LeagueConfig
from app.projections.snapshot import Snapshot
from app.season.performance import _per_game_scale

STAT_KEYS = ("PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FG3A", "FGM", "FGA", "FTM", "FTA")
SMALL_SAMPLE_GAMES = 3
BASELINE_LABEL = (
    "Projection baseline: the snapshot's per-game projection (learned model blended with ESPN, rookie and "
    "injury-return adjustments) x games actually played. Contribution and expectation are measured on the "
    "same per-game category scale (1 = one category standard deviation of per-game production, not centered, so a player who did not play is 0); cumulative values multiply by games."
)


@dataclass(frozen=True)
class Aggregate:
    player_id: str
    games: int
    periods: int
    minutes: float
    totals: dict[str, float]


def aggregate(records: list[dict[str, Any]]) -> dict[str, Aggregate]:
    """Sum stored period rows per player (one player may appear in several periods)."""
    acc: dict[str, dict[str, Any]] = {}
    for r in records:
        a = acc.setdefault(
            r["player_id"], {"games": 0, "periods": set(), "minutes": 0.0, "totals": dict.fromkeys(STAT_KEYS, 0.0)}
        )
        a["games"] += int(r.get("games") or 0)
        if int(r.get("games") or 0) > 0:
            a["periods"].add(int(r["period"]))  # weeks in which the player actually played for the team
        a["minutes"] += float(r.get("minutes") or 0.0)
        for k in STAT_KEYS:
            a["totals"][k] += float((r.get("stats") or {}).get(k) or 0.0)
    return {pid: Aggregate(pid, a["games"], len(a["periods"]), a["minutes"], a["totals"]) for pid, a in acc.items()}


def _per_game_matrix(agg: Aggregate) -> np.ndarray:
    m = np.zeros(len(PRIMITIVES))
    if agg.games > 0:
        for k in STAT_KEYS:
            m[PRIM_IDX[k]] = agg.totals[k] / agg.games
        m[PRIM_IDX["MIN"]] = agg.minutes / agg.games
    m[PRIM_IDX["GP"]] = 1.0
    return m


def _z(matrix: np.ndarray, league: LeagueConfig, info) -> np.ndarray:
    """Production in category-standard-deviation units, NOT centered on the pool median: a player who
    did not play contributes exactly zero, and a bench player's real production still counts as
    positive. Ratio categories use impact against the pool benchmark rate (a poor shooter is negative)."""
    raw = raw_category_matrix(matrix, league.categories, info.benchmark_rates)
    signs = np.array([1.0 if c.higher_is_better else -1.0 for c in league.categories])
    return (raw / info.scales) * signs


def _rates(t: dict[str, float]) -> dict[str, float | None]:
    return {
        "FG_PCT": (t["FGM"] / t["FGA"]) if t.get("FGA") else None,
        "FT_PCT": (t["FTM"] / t["FTA"]) if t.get("FTA") else None,
    }


def rank_performers(
    snap: Snapshot, state: DraftState, records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(contributors, overperformers): rows with the fields of ``schemas.PerformerRow`` minus ``player``/``rank``."""
    league = state.league
    info = _per_game_scale(snap, league)
    keys = [c.key for c in league.categories]
    aggs = aggregate(records)
    if not aggs:
        return [], []
    pids = [p for p in aggs if p in snap.index]
    idx = [snap.index[p] for p in pids]
    actual_pg = np.array([_per_game_matrix(aggs[p]) for p in pids]) if pids else np.zeros((0, len(PRIMITIVES)))
    proj_pg = snap.per_game[idx].copy() if idx else np.zeros((0, len(PRIMITIVES)))
    if len(idx):
        proj_pg[:, PRIM_IDX["GP"]] = 1.0
    z_act = _z(actual_pg, league, info) if len(idx) else np.zeros((0, len(keys)))
    z_proj = _z(proj_pg, league, info) if len(idx) else np.zeros((0, len(keys)))
    rows = []
    for r, pid in enumerate(pids):
        a = aggs[pid]
        i = idx[r]
        has_baseline = not str(snap.projection_source[i]).startswith("prior")
        games = a.games
        v_act = float(z_act[r].sum()) if games > 0 else 0.0
        v_proj = float(z_proj[r].sum())
        contribution = v_act * games
        expected_contribution = v_proj * games if has_baseline else None
        over = (contribution - expected_contribution) if (has_baseline and games > 0) else None
        flags = []
        if games == 0:
            flags.append("no games")
        elif games < SMALL_SAMPLE_GAMES:
            flags.append("small sample")
        if not has_baseline:
            flags.append("no baseline")
        proj_tot = {k: float(proj_pg[r, PRIM_IDX[k]]) * games for k in STAT_KEYS}
        actual = {**{k: a.totals[k] for k in STAT_KEYS}, **_rates(a.totals)}
        expected = {**proj_tot, **_rates(proj_tot)} if has_baseline else None
        actual_pg_d = {**{k: (a.totals[k] / games if games else None) for k in STAT_KEYS}, **_rates(a.totals)}
        expected_pg_d = (
            {**{k: float(proj_pg[r, PRIM_IDX[k]]) for k in STAT_KEYS}, **_rates(proj_tot)} if has_baseline else None
        )
        rows.append(
            {
                "player_id": pid,
                "games": games,
                "periods": a.periods,
                "minutes": round(a.minutes, 1),
                "contribution": round(contribution, 3),
                "contribution_per_game": round(v_act, 3) if games else None,
                "expected_contribution": round(expected_contribution, 3) if expected_contribution is not None else None,
                "over_expected": round(over, 3) if over is not None else None,
                "over_expected_per_game": round(over / games, 3) if over is not None else None,
                "actual": {k: (round(v, 3) if v is not None else None) for k, v in actual.items()},
                "expected": (
                    {k: (round(v, 3) if v is not None else None) for k, v in expected.items()} if expected else None
                ),
                "actual_per_game": {k: (round(v, 3) if v is not None else None) for k, v in actual_pg_d.items()},
                "expected_per_game": (
                    {k: (round(v, 3) if v is not None else None) for k, v in expected_pg_d.items()}
                    if expected_pg_d
                    else None
                ),
                "category_z": {
                    k: round(float(z_act[r, j] - z_proj[r, j]), 3) if games else 0.0 for j, k in enumerate(keys)
                },
                "contribution_by_category": {
                    k: round(float(z_act[r, j]) * games, 3) if games else 0.0 for j, k in enumerate(keys)
                },
                "expected_by_category": (
                    {k: round(float(z_proj[r, j]) * games, 3) for j, k in enumerate(keys)} if has_baseline else None
                ),
                "flags": flags,
            }
        )
    contributors = sorted(rows, key=lambda x: (-x["contribution"], -x["games"]))
    overperformers = sorted([x for x in rows if x["over_expected"] is not None], key=lambda x: -x["over_expected"])
    return contributors, overperformers


def unit_sizes(snap: Snapshot, league: LeagueConfig) -> tuple[dict[str, float], dict[str, float]]:
    """Per-game amount of each category that equals one contribution unit, and the FG/FT benchmark rates."""
    info = _per_game_scale(snap, league)
    return (
        {k: round(float(s), 4) for k, s in zip(info.keys, info.scales, strict=True)},
        {k: round(float(v), 4) for k, v in info.benchmark_rates.items()},
    )
