"""Season analytics from current rosters: power rankings and matchup odds (pure; no network).

One player-week simulation is shared by every team and pairing (common random numbers), so a
matchup's odds reflect roster differences, not sampling noise. Power rankings use the season
projection (games per week from the snapshot's schedule averages); a specific matchup period uses
the real games in that window and ESPN's OUT / IR status (DEC-27).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.draft.events import DraftState
from app.engine.categories import PRIM_IDX
from app.engine.layer_a import standardized
from app.engine.schedule_model import games_per_week_for_players
from app.engine.simulation import (
    SimConfig,
    category_outcomes,
    category_win_probabilities,
    objective,
    simulate_players_week,
)
from app.league.config import LeagueConfig
from app.projections.snapshot import Snapshot
from app.season.weeks import games_in_window, period_window

N_SCENARIOS = 600
OUT_STATUSES = frozenset({"OUT", "SUSPENSION", "INJURY_RESERVE"})


@dataclass(frozen=True)
class TeamSim:
    manager_id: str
    roster_idx: tuple[int, ...]
    counted_idx: tuple[int, ...]  # starters by projected minutes, IR excluded
    n_ir: int
    n_unknown: int


@dataclass(frozen=True)
class TeamPower:
    manager_id: str
    name: str
    is_user: bool
    expected_cats: float
    rank: int
    cat_win_prob: dict[str, float]
    z: dict[str, float]
    n_players: int
    n_ir: int


@dataclass(frozen=True)
class MatchupOdds:
    period: int
    manager_a: str
    manager_b: str
    expected_a: float
    expected_b: float
    p_win_a: float
    p_tie: float
    p_win_b: float
    cat_p_a: dict[str, float]
    modal_score: tuple[float, float]
    games_a: int
    games_b: int
    notes: tuple[str, ...]


def build_team_sims(snap: Snapshot, state: DraftState, ir_player_ids: frozenset[str]) -> tuple[TeamSim, ...]:
    n_start = len(state.league.starting_slots)
    minutes = snap.per_game[:, PRIM_IDX["MIN"]]
    out = []
    for mid, roster in state.current_rosters().items():
        idx = [snap.index[p] for p in roster if p in snap.index]
        n_unknown = len(roster) - len(idx)
        n_ir = sum(1 for p in roster if p in ir_player_ids)
        eligible = [snap.index[p] for p in roster if p in snap.index and p not in ir_player_ids]
        counted = sorted(eligible, key=lambda i: -minutes[i])[:n_start]
        out.append(TeamSim(mid, tuple(idx), tuple(counted), n_ir, n_unknown))
    return tuple(out)


def simulate_league_week(
    snap: Snapshot,
    league: LeagueConfig,
    teams: tuple[TeamSim, ...],
    seed: int,
    n_scenarios: int = N_SCENARIOS,
    games_per_player: np.ndarray | None = None,
    zero_games: frozenset[str] = frozenset(),
) -> dict[str, np.ndarray]:
    """manager_id -> simulated weekly team totals [S, P] over the counted starters."""
    rng = np.random.default_rng(seed)
    gpw = (
        np.asarray(games_per_player, dtype=float)
        if games_per_player is not None
        else games_per_week_for_players([p.team for p in snap.players], snap.team_games_per_week)
    ).copy()
    for pid in zero_games:
        i = snap.index.get(pid)
        if i is not None:
            gpw[i] = 0.0
    weeks = simulate_players_week(rng, snap.per_game, snap.games, SimConfig(n_scenarios=n_scenarios), gpw)
    totals: dict[str, np.ndarray] = {}
    for t in teams:
        totals[t.manager_id] = (
            weeks[list(t.counted_idx)].sum(axis=0) if t.counted_idx else np.zeros((n_scenarios, weeks.shape[2]))
        )
    return totals


def power_rankings(
    snap: Snapshot,
    state: DraftState,
    seed: int,
    ir_player_ids: frozenset[str] = frozenset(),
    n_scenarios: int = N_SCENARIOS,
) -> tuple[TeamPower, ...]:
    league = state.league
    cats, tie = league.categories, league.tie_rule
    keys = [c.key for c in cats]
    teams = build_team_sims(snap, state, ir_player_ids)
    totals = simulate_league_week(snap, league, teams, seed, n_scenarios)
    z_tot = standardized(snap, league).z_totals
    rows: list[dict[str, Any]] = []
    for t in teams:
        scores, probs = [], []
        for o in teams:
            if o.manager_id == t.manager_id:
                continue
            out = category_outcomes(totals[t.manager_id], totals[o.manager_id], cats, tie)
            scores.append(float(objective(out, league.scoring_format, tie).mean()))
            probs.append(category_win_probabilities(out))
        z = z_tot[list(t.counted_idx)].sum(axis=0) if t.counted_idx else np.zeros(len(keys))
        rows.append(
            {
                "manager_id": t.manager_id,
                "expected_cats": float(np.mean(scores)) if scores else 0.0,
                "cat_win_prob": dict(zip(keys, np.mean(probs, axis=0).tolist(), strict=True))
                if probs
                else dict.fromkeys(keys, 0.0),
                "z": dict(zip(keys, z.tolist(), strict=True)),
                "n_players": len(t.roster_idx) + t.n_unknown,
                "n_ir": t.n_ir,
            }
        )
    order = sorted(range(len(rows)), key=lambda i: -rows[i]["expected_cats"])
    ranks = {rows[i]["manager_id"]: r + 1 for r, i in enumerate(order)}
    names = {m.id: m.name for m in league.managers}
    return tuple(
        TeamPower(
            manager_id=r["manager_id"],
            name=names[r["manager_id"]],
            is_user=r["manager_id"] == league.user_manager_id,
            expected_cats=round(r["expected_cats"], 4),
            rank=ranks[r["manager_id"]],
            cat_win_prob={k: round(v, 4) for k, v in r["cat_win_prob"].items()},
            z={k: round(v, 3) for k, v in r["z"].items()},
            n_players=r["n_players"],
            n_ir=r["n_ir"],
        )
        for r in sorted(rows, key=lambda r: ranks[r["manager_id"]])
    )


def _period_games(
    snap: Snapshot, schedule: pd.DataFrame | None, season: str, period: int, notes: list[str]
) -> np.ndarray | None:
    if schedule is None:
        notes.append("schedule not loaded; using season-average games per week")
        return None
    start, end = period_window(season, period)
    counts = games_in_window(schedule, start, end)
    if not counts:
        notes.append(f"no games found for period {period} ({start}..{end}); using season-average games per week")
        return None
    return np.array([float(counts.get(p.team or "", 0)) for p in snap.players])


def matchup_odds(
    snap: Snapshot,
    state: DraftState,
    a: str,
    b: str,
    period: int,
    seed: int,
    schedule: pd.DataFrame | None,
    status: dict[str, dict[str, Any]],
    ir_player_ids: frozenset[str],
    n_scenarios: int = N_SCENARIOS,
) -> MatchupOdds:
    league = state.league
    cats, tie = league.categories, league.tie_rule
    notes: list[str] = []
    games = _period_games(snap, schedule, league.season, period, notes)
    sims = {t.manager_id: t for t in build_team_sims(snap, state, ir_player_ids)}
    involved = state.current_roster(a) + state.current_roster(b)
    zero = frozenset(p for p in involved if (status.get(p, {}).get("injury_status") or "").upper() in OUT_STATUSES) | (
        frozenset(p for p in involved if p in ir_player_ids)
    )
    for pid in sorted(zero):
        i = snap.index.get(pid)
        if i is not None:
            notes.append(f"{snap.players[i].name} is OUT / on IR: 0 games this week")
    totals = simulate_league_week(snap, league, (sims[a], sims[b]), seed, n_scenarios, games, zero)
    out = category_outcomes(totals[a], totals[b], cats, tie)
    obj_a = objective(out, league.scoring_format, tie)
    obj_b = objective(-out, league.scoring_format, tie)
    modal = Counter(zip(obj_a.tolist(), obj_b.tolist(), strict=True)).most_common(1)[0][0]

    def games_for(t: TeamSim) -> int:
        if games is None:
            return 0
        return int(sum(games[i] for i in t.counted_idx if snap.players[i].player_id not in zero))

    return MatchupOdds(
        period=period,
        manager_a=a,
        manager_b=b,
        expected_a=round(float(obj_a.mean()), 4),
        expected_b=round(float(obj_b.mean()), 4),
        p_win_a=float((obj_a > obj_b).mean()),
        p_tie=float((obj_a == obj_b).mean()),
        p_win_b=float((obj_a < obj_b).mean()),
        cat_p_a={c.key: round(float(v), 4) for c, v in zip(cats, category_win_probabilities(out), strict=True)},
        modal_score=(float(modal[0]), float(modal[1])),
        games_a=games_for(sims[a]),
        games_b=games_for(sims[b]),
        notes=tuple(notes),
    )
