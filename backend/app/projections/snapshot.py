"""The engine's data snapshot: players + aligned projection arrays, saved as parquet + json.

Every recommendation is computed from exactly one snapshot, identified by ``snapshot_id``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from app.engine.categories import PRIM_IDX, PRIMITIVES
from app.identity.players import Player

SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    label: str
    source: str  # "demo" | "nba"
    season: str
    created_at: str
    players: tuple[Player, ...]
    per_game: np.ndarray  # [n, len(PRIMITIVES)]; MIN = minutes/game, GP = projected games
    per_game_sd: np.ndarray  # [n, len(PRIMITIVES)] sd of the per-game mean (GP column = games sd)
    adp: np.ndarray  # [n], nan when unknown
    rank: np.ndarray  # [n], nan when unknown
    projection_source: tuple[str, ...]
    adp_platform: str | None = None
    adp_asof: str | None = None
    rank_source: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    is_demo: bool = False
    team_games_per_week: dict[str, float] = field(default_factory=dict)  # empty -> generic 3.5 games/week
    schedule_label: str = "generic 3.5 games/week assumption (no schedule loaded)"

    @cached_property
    def index(self) -> dict[str, int]:
        return {p.player_id: i for i, p in enumerate(self.players)}

    @property
    def n(self) -> int:
        return len(self.players)

    @property
    def games(self) -> np.ndarray:
        return self.per_game[:, PRIM_IDX["GP"]]

    def totals(self) -> np.ndarray:
        """Season-total view: per-game stats × projected games (MIN and GP columns kept as-is)."""
        t = self.per_game * self.games[:, None]
        t[:, PRIM_IDX["MIN"]] = self.per_game[:, PRIM_IDX["MIN"]]
        t[:, PRIM_IDX["GP"]] = self.games
        return t

    def positions(self) -> list[frozenset[str]]:
        return [p.eligible_positions for p in self.players]

    def primary_positions(self) -> list[str | None]:
        return [p.primary_position for p in self.players]

    # --- persistence ----------------------------------------------------------------------
    def save(self, directory: str | Path) -> Path:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        cols: dict[str, Any] = {"player_id": [p.player_id for p in self.players]}
        for k in PRIMITIVES:
            cols[f"pg_{k}"] = self.per_game[:, PRIM_IDX[k]]
            cols[f"sd_{k}"] = self.per_game_sd[:, PRIM_IDX[k]]
        cols["adp"] = self.adp
        cols["rank"] = self.rank
        cols["projection_source"] = list(self.projection_source)
        pq.write_table(pa.table(cols), d / "projections.parquet")
        (d / "players.json").write_text(json.dumps([p.to_dict() for p in self.players]))
        meta = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "label": self.label,
            "source": self.source,
            "season": self.season,
            "created_at": self.created_at,
            "adp_platform": self.adp_platform,
            "adp_asof": self.adp_asof,
            "rank_source": self.rank_source,
            "provenance": self.provenance,
            "health": self.health,
            "is_demo": self.is_demo,
            "team_games_per_week": self.team_games_per_week,
            "schedule_label": self.schedule_label,
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
        return d

    @staticmethod
    def load(directory: str | Path) -> Snapshot:
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text())
        if meta.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"unsupported snapshot schema {meta.get('schema_version')}")
        players = tuple(Player.from_dict(x) for x in json.loads((d / "players.json").read_text()))
        t = pq.read_table(d / "projections.parquet").to_pydict()
        n = len(players)
        if t["player_id"] != [p.player_id for p in players]:
            raise ValueError("snapshot players.json and projections.parquet are misaligned")
        pg = np.zeros((n, len(PRIMITIVES)))
        sd = np.zeros((n, len(PRIMITIVES)))
        for k in PRIMITIVES:
            pg[:, PRIM_IDX[k]] = np.asarray(t[f"pg_{k}"], dtype=float)
            sd[:, PRIM_IDX[k]] = np.asarray(t[f"sd_{k}"], dtype=float)
        return Snapshot(
            meta["snapshot_id"],
            meta["label"],
            meta["source"],
            meta["season"],
            meta["created_at"],
            players,
            pg,
            sd,
            np.asarray(t["adp"], dtype=float),
            np.asarray(t["rank"], dtype=float),
            tuple(t["projection_source"]),
            meta.get("adp_platform"),
            meta.get("adp_asof"),
            meta.get("rank_source"),
            meta.get("provenance", {}),
            meta.get("health", {}),
            bool(meta.get("is_demo", False)),
            meta.get("team_games_per_week", {}),
            meta.get("schedule_label", "generic 3.5 games/week assumption (no schedule loaded)"),
        )


def content_hash(*arrays: np.ndarray) -> str:
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()[:12]


def validate_snapshot(s: Snapshot) -> list[str]:
    """Coherence checks: nonnegative, makes <= attempts, 3PM <= FGM, 3PA <= FGA, games bounded."""
    problems: list[str] = []
    pg = s.per_game
    if pg.shape != (s.n, len(PRIMITIVES)):
        return [f"per_game shape {pg.shape} != ({s.n}, {len(PRIMITIVES)})"]
    if np.any(pg < -1e-9):
        bad = np.argwhere(pg < -1e-9)
        problems.append(
            f"{len(bad)} negative per-game values (first: {s.players[bad[0][0]].name} {PRIMITIVES[bad[0][1]]})"
        )
    for num, den in (("FGM", "FGA"), ("FTM", "FTA"), ("FG3M", "FG3A"), ("FG3M", "FGM"), ("FG3A", "FGA")):
        viol = pg[:, PRIM_IDX[num]] > pg[:, PRIM_IDX[den]] + 1e-9
        if viol.any():
            problems.append(f"{int(viol.sum())} players with {num} > {den}")
    if np.any(s.games > 82 + 1e-9):
        problems.append("projected games above 82")
    if len(s.projection_source) != s.n:
        problems.append("projection_source length mismatch")
    if len({p.player_id for p in s.players}) != s.n:
        problems.append("duplicate player ids")
    return problems
