"""Opponent demand model and stochastic draft completion (rollouts).

Opponents pick from the top of a demand ordering (ESPN ADP when present, otherwise value order
labeled as a proxy) with positional need and noise. The user's own future picks follow a fixed,
feasible continuation policy so candidate scenarios are strategically comparable.
Common random numbers: callers pass a pre-drawn uniform matrix ``u[scenario, pick_index]`` so the
same opponent "luck" is reused across candidates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.draft.schedule import Pick
from app.engine.lineup import assign_lineup, roster_slots
from app.league.config import LeagueConfig
from app.projections.snapshot import Snapshot

TOP_K = 14  # opponents choose among the next K players in demand order
NEED_BONUS = 0.6  # multiplicative boost for a player who fills an opponent's open starting slot


@dataclass(frozen=True)
class DemandModel:
    key: np.ndarray  # [n] lower = expected to go earlier
    has_adp: np.ndarray  # [n]
    label: str  # "adp:<platform>" | "value_proxy"
    temperature: float  # demand-key units; larger = noisier opponents

    @property
    def is_proxy(self) -> bool:
        return self.label == "value_proxy"


def build_demand(snapshot: Snapshot, base_value: np.ndarray, temperature: float = 6.0) -> DemandModel:
    adp = snapshot.adp
    has = np.isfinite(adp)
    # players without ADP are slotted after the known-ADP tail in value order
    value_rank = np.argsort(np.argsort(-base_value, kind="stable")).astype(float)
    tail = float(np.nanmax(adp)) if has.any() else 0.0
    key = np.where(has, adp, tail + 1.0 + value_rank)
    if has.sum() < 50:
        return DemandModel(value_rank + 1.0, has, "value_proxy", temperature)
    return DemandModel(key, has, f"adp:{snapshot.adp_platform or 'unknown'}", temperature)


def _open_slots(
    positions: list[frozenset[str]], roster_idx: list[int], slots: tuple[str, ...], n_start: int
) -> list[str]:
    a = assign_lineup([positions[i] for i in roster_idx], slots, n_start)
    return [slots[j] for j in a.open_slot_indices if j < n_start]


def fills_any(pos: frozenset[str], open_slots: list[str]) -> bool:
    from app.engine.lineup import slot_accepts

    return any(slot_accepts(s, pos) for s in open_slots)


def opponent_choice(
    available: np.ndarray,
    demand: DemandModel,
    positions: list[frozenset[str]],
    open_slots: list[str],
    u: float,
    order: np.ndarray,
) -> int:
    """Pick index for an opponent given a uniform draw ``u`` (inverse-CDF over softmax weights).

    ``order`` is the demand ordering (indices sorted by demand.key) to avoid re-sorting.
    """
    cands: list[int] = []
    for i in order:
        if available[i]:
            cands.append(int(i))
            if len(cands) >= TOP_K:
                break
    if not cands:
        raise ValueError("no available players")
    keys = demand.key[cands]
    w = np.exp(-(keys - keys[0]) / max(demand.temperature, 1e-6))
    if open_slots:
        need = np.array([1.0 + NEED_BONUS if fills_any(positions[i], open_slots) else 1.0 for i in cands])
        w = w * need
    cdf = np.cumsum(w) / w.sum()
    j = int(np.searchsorted(cdf, u, side="right"))
    return cands[min(j, len(cands) - 1)]


def cap_mask(
    available: np.ndarray,
    roster_idx: list[int],
    primaries: list[str | None],
    caps: dict[str, int],
    by_pos: dict[str, np.ndarray],
) -> np.ndarray:
    """Availability mask with primary positions whose roster cap is already reached removed."""
    if not caps:
        return available
    counts: dict[str, int] = {}
    for i in roster_idx:
        pp = primaries[i]
        if pp in caps:
            counts[pp] = counts.get(pp, 0) + 1
    out = available
    for pos, cap in caps.items():
        if counts.get(pos, 0) >= cap and pos in by_pos:
            if out is available:
                out = available.copy()
            out[by_pos[pos]] = False
    return out


def user_policy_choice(
    available: np.ndarray,
    base_value: np.ndarray,
    positions: list[frozenset[str]],
    roster_idx: list[int],
    league: LeagueConfig,
    remaining_user_picks: int,
) -> int:
    """Continuation policy: best strategy value among players that keep the roster completable.

    Prefers players filling an open starting slot when the number of open starting slots equals the
    remaining picks (otherwise coverage would be lost); else best available value.
    """
    slots = roster_slots(league)
    n_start = len(league.starting_slots)
    open_slots = _open_slots(positions, roster_idx, slots, n_start)
    must_fill = len(open_slots) >= remaining_user_picks
    order = np.argsort(-base_value, kind="stable")
    fallback = None
    for i in order:
        if not available[i]:
            continue
        if fallback is None:
            fallback = int(i)
        if not must_fill or fills_any(positions[i], open_slots):
            return int(i)
    if fallback is None:
        raise ValueError("no available players")
    return fallback


@dataclass(frozen=True)
class Rollout:
    picks: dict[int, int]  # overall -> player idx chosen in this rollout (future picks only)
    rosters: dict[str, list[int]]  # manager -> all player idxs at the end


def rollout_draft(
    snapshot: Snapshot,
    league: LeagueConfig,
    schedule: tuple[Pick, ...],
    current_picks: dict[int, str],
    drafted: frozenset[str],
    base_value: np.ndarray,
    demand: DemandModel,
    u_row: np.ndarray,
    forced: dict[int, int] | None = None,
    stop_after_overall: int | None = None,
    user_targets: list[int] | None = None,
) -> Rollout:
    """Complete the draft from the first open pick.

    ``forced`` maps overall -> player idx the user takes at that pick (candidate under test).
    ``user_targets`` is an ordered wish list for the user's later picks (take the first still
    available target, else the policy). ``u_row`` provides one uniform per schedule pick.
    """
    n = snapshot.n
    positions = snapshot.positions()
    available = np.ones(n, dtype=bool)
    for pid in drafted:
        i = snapshot.index.get(pid)
        if i is not None:
            available[i] = False
    rosters: dict[str, list[int]] = {m.id: [] for m in league.managers}
    for overall, pid in current_picks.items():
        i = snapshot.index.get(pid)
        if i is not None:
            rosters[_owner(schedule, overall)].append(i)
    slots = roster_slots(league)
    n_start = len(league.starting_slots)
    order = np.argsort(demand.key, kind="stable")
    uid = league.user_manager_id
    primaries = snapshot.primary_positions()
    by_pos: dict[str, np.ndarray] = {}
    if league.position_caps:
        for pos in league.position_caps:
            by_pos[pos] = np.array([i for i, pp in enumerate(primaries) if pp == pos], dtype=int)
    future: dict[int, int] = {}
    user_remaining = sum(1 for p in schedule if p.manager_id == uid and p.overall not in current_picks)
    for p in schedule:
        if p.overall in current_picks:
            continue
        if forced and p.overall in forced:
            i = forced[p.overall]
            if not available[i]:
                raise ValueError("forced player not available")
        elif p.manager_id == uid:
            legal = cap_mask(available, rosters[uid], primaries, league.position_caps, by_pos)
            i = None
            if user_targets:
                for t in user_targets:
                    if legal[t]:
                        i = t
                        break
            if i is None:
                i = user_policy_choice(legal, base_value, positions, rosters[uid], league, user_remaining)
        else:
            legal = cap_mask(available, rosters[p.manager_id], primaries, league.position_caps, by_pos)
            open_slots = _open_slots(positions, rosters[p.manager_id], slots, n_start)
            i = opponent_choice(legal, demand, positions, open_slots, float(u_row[p.overall - 1]), order)
        available[i] = False
        rosters[p.manager_id].append(i)
        future[p.overall] = i
        if p.manager_id == uid:
            user_remaining -= 1
        if stop_after_overall is not None and p.overall >= stop_after_overall:
            break
    return Rollout(future, rosters)


def _owner(schedule: tuple[Pick, ...], overall: int) -> str:
    return schedule[overall - 1].manager_id
