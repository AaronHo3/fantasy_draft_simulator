"""Actual vs projected production, per player and per matchup period.

``performance_table`` scores every rostered player's real box scores in a period window against the
snapshot's per-game projection on the projection's own per-game z scale (same centers and scales
for both), so "value_delta" reads as categories-worth of over/under-performance per game.
``append_tracker`` keeps a long CSV, one row per player per period, that a spreadsheet can plot.
``free_agent_hot_starts`` ranks unowned players by what they have actually produced so far.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.draft.events import DraftState
from app.engine.categories import PRIM_IDX, PRIMITIVES, raw_category_matrix, standardize
from app.engine.layer_a import standardized
from app.league.config import LeagueConfig
from app.projections.snapshot import Snapshot
from app.season.tracker import COLS

STAT_KEYS = tuple(k for k in COLS if k != "MIN")  # PTS .. TOV
RATE_COLS = {"FG_PCT": ("fgm", "fga"), "FT_PCT": ("ftm", "fta")}


def player_week_lines(logs: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Per-game averages per nba_id over the games dated in [start, end] (empty frame when none)."""
    if logs.empty:
        return pd.DataFrame()
    dates = pd.to_datetime(logs["game_date"]).dt.date
    rows = logs[(dates >= start) & (dates <= end)]
    if rows.empty:
        return pd.DataFrame()
    cols = list(COLS.values())
    g = rows.groupby("nba_id")
    out = g[cols].sum()
    out["games"] = g.size()
    for c in cols:
        out[c] = out[c] / out["games"]
    out["name"] = g["name"].first()
    return out


def _per_game_scale(snap: Snapshot, league: LeagueConfig):
    """Per-game standardization fitted on the projection pool, reused for actual lines."""
    std = standardized(snap, league)
    pg = snap.per_game.copy()
    pg[:, PRIM_IDX["GP"]] = 1.0
    _, info = standardize(pg, league.categories, std.pool_mask, std.info.method)
    return info


def _values(matrix: np.ndarray, league: LeagueConfig, info) -> np.ndarray:
    raw = raw_category_matrix(matrix, league.categories, info.benchmark_rates)
    z = (raw - info.centers) / info.scales
    signs = np.array([1.0 if c.higher_is_better else -1.0 for c in league.categories])
    return (z * signs).sum(axis=1)


def _line_matrix(lines: pd.DataFrame, nba_ids: list[int | None]) -> tuple[np.ndarray, np.ndarray]:
    """Per-game primitive matrix for the given players from week lines; games=0 rows are zero."""
    m = np.zeros((len(nba_ids), len(PRIMITIVES)))
    games = np.zeros(len(nba_ids))
    for r, nid in enumerate(nba_ids):
        if nid is None or lines.empty or nid not in lines.index:
            continue
        row = lines.loc[nid]
        games[r] = row["games"]
        for k, c in COLS.items():
            m[r, PRIM_IDX[k]] = float(row[c])
        m[r, PRIM_IDX["GP"]] = 1.0
    return m, games


def performance_table(
    snap: Snapshot,
    state: DraftState,
    logs: pd.DataFrame,
    period: int,
    manager_id: str,
    window: tuple[date, date],
) -> pd.DataFrame:
    """One row per rostered player: games played, actual vs projected per game, category deltas, value delta."""
    league = state.league
    info = _per_game_scale(snap, league)
    roster = [p for p in state.current_roster(manager_id) if p in snap.index]
    idx = [snap.index[p] for p in roster]
    lines = player_week_lines(logs, *window)
    actual, games = _line_matrix(lines, [snap.players[i].nba_id for i in idx])
    proj = snap.per_game[idx].copy()
    proj[:, PRIM_IDX["GP"]] = 1.0
    v_act, v_proj = _values(actual, league, info), _values(proj, league, info)
    rows = []
    for r, i in enumerate(idx):
        p = snap.players[i]
        played = games[r] > 0
        row = {
            "period": period,
            "window_start": window[0].isoformat(),
            "window_end": window[1].isoformat(),
            "manager_id": manager_id,
            "player_id": p.player_id,
            "player": p.name,
            "team": p.team,
            "games": int(games[r]),
            "min_actual": actual[r, PRIM_IDX["MIN"]] if played else np.nan,
            "min_proj": proj[r, PRIM_IDX["MIN"]],
        }
        for k in STAT_KEYS:
            c = COLS[k]
            row[f"{c}_proj"] = proj[r, PRIM_IDX[k]]
            row[f"{c}_actual"] = actual[r, PRIM_IDX[k]] if played else np.nan
            row[f"{c}_delta"] = (actual[r, PRIM_IDX[k]] - proj[r, PRIM_IDX[k]]) if played else np.nan
        for key, (mk, ak) in RATE_COLS.items():
            name = key.lower()
            row[f"{name}_proj"] = proj[r, PRIM_IDX[mk.upper()]] / max(proj[r, PRIM_IDX[ak.upper()]], 1e-9)
            row[f"{name}_actual"] = (
                (actual[r, PRIM_IDX[mk.upper()]] / actual[r, PRIM_IDX[ak.upper()]])
                if played and actual[r, PRIM_IDX[ak.upper()]] > 0
                else np.nan
            )
        row["value_proj"] = float(v_proj[r])
        row["value_actual"] = float(v_act[r]) if played else np.nan
        row["value_delta"] = float(v_act[r] - v_proj[r]) if played else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def append_tracker(path: str | Path, table: pd.DataFrame) -> pd.DataFrame:
    """Append a period's rows to the long CSV, replacing rows already stored for that period and manager."""
    path = Path(path)
    if path.exists():
        old = pd.read_csv(path)
        keep = ~(
            (old["period"].isin(table["period"].unique())) & (old["manager_id"].isin(table["manager_id"].unique()))
        )
        merged = pd.concat([old[keep], table], ignore_index=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = table.copy()
    merged = merged.sort_values(["period", "manager_id", "player"]).reset_index(drop=True)
    merged.to_csv(path, index=False)
    return merged


def free_agent_hot_starts(
    snap: Snapshot,
    state: DraftState,
    logs: pd.DataFrame,
    status: dict[str, dict],
    window: tuple[date, date],
    limit: int = 30,
) -> pd.DataFrame:
    """Unowned players with at least one game in the window, ranked by actual per-game value."""
    league = state.league
    info = _per_game_scale(snap, league)
    lines = player_week_lines(logs, *window)
    cands = [
        p
        for p in snap.players
        if p.player_id not in state.owned_player_ids
        and p.nba_id is not None
        and not lines.empty
        and p.nba_id in lines.index
    ]
    if not cands:
        return pd.DataFrame()
    idx = [snap.index[p.player_id] for p in cands]
    actual, games = _line_matrix(lines, [p.nba_id for p in cands])
    proj = snap.per_game[idx].copy()
    proj[:, PRIM_IDX["GP"]] = 1.0
    v_act, v_proj = _values(actual, league, info), _values(proj, league, info)
    rows = []
    for r, p in enumerate(cands):
        s = status.get(p.player_id, {})
        row = {
            "player_id": p.player_id,
            "player": p.name,
            "team": p.team,
            "pos": "/".join(sorted(p.eligible_positions)),
            "status": s.get("injury_status"),
            "owned_pct": s.get("percent_owned"),
            "games": int(games[r]),
            "min_actual": actual[r, PRIM_IDX["MIN"]],
            "min_proj": proj[r, PRIM_IDX["MIN"]],
        }
        for k in STAT_KEYS:
            row[f"{COLS[k]}_actual"] = actual[r, PRIM_IDX[k]]
            row[f"{COLS[k]}_proj"] = proj[r, PRIM_IDX[k]]
        row["value_actual"], row["value_proj"], row["value_delta"] = (
            float(v_act[r]),
            float(v_proj[r]),
            float(v_act[r] - v_proj[r]),
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("value_actual", ascending=False).head(limit).reset_index(drop=True)
