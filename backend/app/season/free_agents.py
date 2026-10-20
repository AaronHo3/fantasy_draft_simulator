"""Free agents ranked by what they add to the user's current roster, with the best drop for each."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.draft.events import DraftState
from app.engine.categories import PRIM_IDX
from app.engine.layer_a import rank_layer_a, standardized
from app.identity.players import normalize_name
from app.projections.snapshot import Snapshot
from app.recommend.service import user_context
from app.season.power import OUT_STATUSES


@dataclass(frozen=True)
class FreeAgent:
    player_id: str
    score: float
    z: dict[str, float]
    best_drop: str | None
    drop_value: float
    swap_delta: float
    injury_status: str | None
    percent_owned: float | None
    flags: tuple[str, ...]


def _is_out(status: dict[str, dict[str, Any]], pid: str) -> bool:
    return (status.get(pid, {}).get("injury_status") or "").upper() in OUT_STATUSES


def _best_drop(snap: Snapshot, state: DraftState, weights: np.ndarray, ir: frozenset[str]) -> tuple[str | None, float]:
    """Roster player (not on IR) whose removal costs the least weighted z; ties -> fewest minutes."""
    z = standardized(snap, state.league).z_totals
    minutes = snap.per_game[:, PRIM_IDX["MIN"]]
    best: tuple[float, float, str] | None = None
    for pid in state.current_roster(state.league.user_manager_id):
        i = snap.index.get(pid)
        if i is None or pid in ir:
            continue
        key = (float(z[i] @ weights), float(minutes[i]), pid)
        if best is None or key < best:
            best = key
    return (best[2], best[0]) if best else (None, 0.0)


def free_agents(
    snap: Snapshot,
    state: DraftState,
    status: dict[str, dict[str, Any]],
    ir_player_ids: frozenset[str],
    limit: int = 50,
    position: str | None = None,
    q: str | None = None,
) -> tuple[FreeAgent, ...]:
    res = rank_layer_a(user_context(state, snap))
    drop_id, drop_value = _best_drop(snap, state, res.weights, ir_player_ids)
    needle = normalize_name(q) if q else None
    rows: list[FreeAgent] = []
    for c in res.candidates:
        p = snap.players[c.idx]
        if position and position not in p.eligible_positions:
            continue
        if needle and needle not in normalize_name(p.name):
            continue
        st = status.get(p.player_id, {})
        flags = ["out"] if _is_out(status, p.player_id) else []
        if (st.get("injury_status") or "").upper() == "DAY_TO_DAY":
            flags.append("day-to-day")
        rows.append(
            FreeAgent(
                player_id=p.player_id,
                score=round(float(c.base_value), 4),
                z={k: round(float(v), 3) for k, v in zip(res.keys, c.z, strict=True)},
                best_drop=drop_id,
                drop_value=round(drop_value, 4),
                swap_delta=round(float(c.base_value) - round(drop_value, 4), 4),
                injury_status=st.get("injury_status"),
                percent_owned=st.get("percent_owned"),
                flags=tuple(flags),
            )
        )
    rows.sort(key=lambda f: ("out" in f.flags, -f.score))
    return tuple(rows[:limit])
