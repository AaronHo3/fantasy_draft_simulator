"""Legal player-to-slot assignment via bipartite matching, roster caps, completion feasibility.

A multi-eligible player fills exactly one slot. Starting slots are preferred over bench. Primary-
position caps are a separate counting constraint applied on the player's ESPN primary position.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.league.config import SLOT_COMPATIBILITY, LeagueConfig

INFEASIBLE = 1_000_000.0
BENCH_COST = 1.0  # prefer filling starting slots (cost 0) before bench slots
UNKNOWN_ELIGIBILITY_COST = 0.25  # legal but discouraged when eligibility is unverified


def slot_accepts(slot: str, positions: frozenset[str]) -> bool:
    return bool(SLOT_COMPATIBILITY[slot] & positions)


@dataclass(frozen=True)
class Assignment:
    slots: tuple[str, ...]  # starting slots then bench slots
    assigned: dict[int, int]  # player index -> slot index
    unassigned_players: tuple[int, ...]
    open_slot_indices: tuple[int, ...]

    @property
    def legal(self) -> bool:
        return len(self.unassigned_players) == 0

    def slot_of(self, player_idx: int) -> str | None:
        j = self.assigned.get(player_idx)
        return None if j is None else self.slots[j]

    def open_slots(self) -> list[str]:
        return [self.slots[j] for j in self.open_slot_indices]


def roster_slots(cfg: LeagueConfig) -> tuple[str, ...]:
    return tuple(cfg.starting_slots) + tuple(["BENCH"] * cfg.bench_slots)


def assign_lineup(
    player_positions: list[frozenset[str]],
    slots: tuple[str, ...] | list[str],
    n_starting: int | None = None,
    unverified: list[bool] | None = None,
) -> Assignment:
    """Maximum legal matching of players to slots, preferring starting slots.

    Players with an empty position set cannot be assigned anywhere (they stay unassigned, which
    makes the roster illegal, surfacing the problem instead of hiding it).
    """
    slots = tuple(slots)
    n_p, n_s = len(player_positions), len(slots)
    if n_starting is None:
        n_starting = sum(1 for s in slots if s != "BENCH")
    if n_p == 0:
        return Assignment(slots, {}, (), tuple(range(n_s)))
    cost = np.full((n_p, n_s), INFEASIBLE)
    for i, pos in enumerate(player_positions):
        for j, s in enumerate(slots):
            if slot_accepts(s, pos):
                c = BENCH_COST if j >= n_starting else 0.0
                if unverified and unverified[i]:
                    c += UNKNOWN_ELIGIBILITY_COST
                cost[i, j] = c
    rows, cols = linear_sum_assignment(cost)
    assigned = {int(i): int(j) for i, j in zip(rows, cols, strict=True) if cost[i, j] < INFEASIBLE}
    unassigned = tuple(i for i in range(n_p) if i not in assigned)
    used = set(assigned.values())
    open_idx = tuple(j for j in range(n_s) if j not in used)
    return Assignment(slots, assigned, unassigned, open_idx)


@dataclass(frozen=True)
class CapCheck:
    ok: bool
    counts: dict[str, int]
    violations: dict[str, int] = field(default_factory=dict)  # position -> excess
    room: dict[str, int] = field(default_factory=dict)  # position -> remaining allowed


def check_position_caps(cfg: LeagueConfig, primary_positions: list[str | None]) -> CapCheck:
    counts: dict[str, int] = {}
    for p in primary_positions:
        if p:
            counts[p] = counts.get(p, 0) + 1
    violations = {p: counts.get(p, 0) - cap for p, cap in cfg.position_caps.items() if counts.get(p, 0) > cap}
    room = {p: cap - counts.get(p, 0) for p, cap in cfg.position_caps.items()}
    return CapCheck(not violations, counts, violations, room)


@dataclass(frozen=True)
class CoverageReport:
    legal: bool  # every rostered player fits a slot
    caps_ok: bool
    starting_filled: int
    starting_total: int
    open_starting_slots: tuple[str, ...]
    bench_used: int
    completion_feasible: bool  # open starting slots can still be filled with remaining picks
    completion_detail: str
    assignment: Assignment
    caps: CapCheck

    @property
    def coverage_ratio(self) -> float:
        return self.starting_filled / self.starting_total if self.starting_total else 1.0


def completion_feasible(
    open_slots: list[str], remaining_picks: int, available_positions: list[frozenset[str]]
) -> tuple[bool, str]:
    """Can ``open_slots`` be filled by distinct available players within ``remaining_picks``?

    Uses a maximum matching between open slots and distinct available players.
    """
    if not open_slots:
        return True, "all starting slots filled"
    if remaining_picks < len(open_slots):
        return False, f"{len(open_slots)} open starting slots but only {remaining_picks} picks left"
    if not available_positions:
        return False, "no available players"
    cost = np.full((len(open_slots), len(available_positions)), INFEASIBLE)
    for j, s in enumerate(open_slots):
        for i, pos in enumerate(available_positions):
            if slot_accepts(s, pos):
                cost[j, i] = 0.0
    rows, cols = linear_sum_assignment(cost)
    matched = int(sum(1 for r, c in zip(rows, cols, strict=True) if cost[r, c] < INFEASIBLE))
    if matched < len(open_slots):
        missing = [
            open_slots[j]
            for j in range(len(open_slots))
            if j not in {r for r, c in zip(rows, cols, strict=True) if cost[r, c] < INFEASIBLE}
        ]
        return False, f"no available eligible players for slots {missing}"
    return True, "fillable from available players"


def evaluate_roster(
    cfg: LeagueConfig,
    player_positions: list[frozenset[str]],
    primary_positions: list[str | None],
    remaining_picks: int,
    available_positions: list[frozenset[str]],
    unverified: list[bool] | None = None,
) -> CoverageReport:
    slots = roster_slots(cfg)
    n_start = len(cfg.starting_slots)
    a = assign_lineup(player_positions, slots, n_start, unverified)
    caps = check_position_caps(cfg, primary_positions)
    open_start = [slots[j] for j in a.open_slot_indices if j < n_start]
    filled = n_start - len(open_start)
    bench_used = sum(1 for j in a.assigned.values() if j >= n_start)
    # future picks cannot use primary positions whose cap is exhausted
    if cfg.position_caps:
        avail = [p for p in available_positions]
    else:
        avail = available_positions
    feasible, detail = completion_feasible(open_start, remaining_picks, avail)
    return CoverageReport(a.legal, caps.ok, filled, n_start, tuple(open_start), bench_used, feasible, detail, a, caps)
