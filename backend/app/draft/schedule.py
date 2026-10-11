"""Ordered pick schedule: snake / linear / third-round reversal, keepers, traded picks, edits.

Managers are stable ids; display names live in the league config.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.league.config import LeagueConfig


@dataclass(frozen=True)
class Pick:
    overall: int  # 1-based
    round: int  # 1-based
    pick_in_round: int  # 1-based
    manager_id: str  # who makes this pick (after trades)
    original_manager_id: str  # whose slot it was in the base order
    keeper_player_id: str | None = None  # pre-committed keeper occupies the pick


def _round_order(base: list[str], rnd: int, draft_type: str, third_round_reversal: bool) -> list[str]:
    if draft_type == "linear":
        return list(base)
    if third_round_reversal:
        # R1 forward, R2 reverse, R3 reverse, then alternate from R4: fwd, rev, ...
        if rnd == 1:
            return list(base)
        if rnd in (2, 3):
            return list(reversed(base))
        return list(base) if rnd % 2 == 0 else list(reversed(base))
    return list(base) if rnd % 2 == 1 else list(reversed(base))


def build_pick_schedule(cfg: LeagueConfig, overrides: dict[int, str] | None = None) -> list[Pick]:
    """Full ordered schedule for ``cfg.n_rounds`` rounds.

    ``overrides`` maps overall pick -> manager id for manual edits (applied last).
    """
    n = cfg.n_managers
    picks: list[Pick] = []
    traded = {(t.round, t.from_manager_id): t.to_manager_id for t in cfg.traded_picks}
    keepers = {(k.round, k.manager_id): k.player_id for k in cfg.keepers}
    overall = 0
    for rnd in range(1, cfg.n_rounds + 1):
        order = _round_order(cfg.draft_order, rnd, cfg.draft_type, cfg.third_round_reversal)
        for j, original in enumerate(order, start=1):
            overall += 1
            owner = traded.get((rnd, original), original)
            picks.append(Pick(overall, rnd, j, owner, original, keepers.get((rnd, owner))))
    if overrides:
        picks = [replace(p, manager_id=overrides.get(p.overall, p.manager_id)) for p in picks]
    assert len(picks) == n * cfg.n_rounds
    return picks


def picks_for_manager(schedule: list[Pick], manager_id: str) -> list[Pick]:
    return [p for p in schedule if p.manager_id == manager_id]


def next_pick_for_manager(schedule: list[Pick], manager_id: str, after_overall: int) -> Pick | None:
    """First pick of ``manager_id`` with overall > after_overall (keeper picks excluded)."""
    for p in schedule:
        if p.overall > after_overall and p.manager_id == manager_id and p.keeper_player_id is None:
            return p
    return None


def picks_between(current_overall: int, next_overall: int) -> int:
    """Number of other managers' selections strictly between two overall picks."""
    return max(0, next_overall - current_overall - 1)
