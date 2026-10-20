"""Live ESPN player status (injury, percent owned) written by sync and overlaid at analysis time.

The projection snapshot stays immutable; this small table is the only thing that moves day to day.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from app.projections.snapshot import Snapshot

LIVE_COLUMNS: tuple[str, ...] = ("espn_id", "injury_status", "percent_owned", "team", "fetched_at")
NO_TEAM = "NO_TEAM"


def write_live_status(live_dir: Path, league_id: int, players: pd.DataFrame) -> Path:
    """Select the live columns from an ``espn_public.parse_players`` frame and write them atomically."""
    missing = [c for c in LIVE_COLUMNS if c not in players.columns]
    if missing:
        raise ValueError(f"players frame lacks columns {missing}")
    out_dir = live_dir / str(league_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "players.parquet"
    tmp = out_dir / "players.parquet.tmp"
    frame = players.loc[:, list(LIVE_COLUMNS)].reset_index(drop=True)
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, target)
    return target


def read_live_status(live_dir: Path, league_id: int) -> pd.DataFrame | None:
    path = live_dir / str(league_id) / "players.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def status_overlay(snap: Snapshot, live: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    """player_id -> {injury_status, percent_owned, fetched_at}; snapshot status when no live row."""
    by_espn: dict[int, dict[str, Any]] = {}
    if live is not None and len(live):
        for row in live.itertuples(index=False):
            eid = getattr(row, "espn_id", None)
            if eid is None or pd.isna(eid):
                continue
            pct = getattr(row, "percent_owned", None)
            team = getattr(row, "team", None)
            team = None if team is None or (isinstance(team, float) and pd.isna(team)) or team == "" else str(team)
            status = None if pd.isna(row.injury_status) else str(row.injury_status)
            by_espn[int(eid)] = {
                # a player ESPN lists with no NBA team (waived, unsigned) cannot play: treated like OUT
                "injury_status": NO_TEAM if team is None else status,
                "percent_owned": None if pct is None or pd.isna(pct) else float(pct),
                "team": team,
                "fetched_at": str(row.fetched_at),
            }
    out: dict[str, dict[str, Any]] = {}
    for p in snap.players:
        hit = by_espn.get(p.espn_id) if p.espn_id else None
        out[p.player_id] = hit or {
            "injury_status": p.injury_status,
            "percent_owned": None,
            "team": p.team,
            "fetched_at": None,
        }
    return out
