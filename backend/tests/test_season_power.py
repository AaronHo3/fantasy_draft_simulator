"""Season analytics on the demo snapshot with a small completed draft."""

from __future__ import annotations

import pandas as pd
import pytest

from app.demo.generate import generate_demo_snapshot
from app.draft.events import EventType
from app.engine.categories import PRIM_IDX
from app.league.config import demo_league_config
from app.persistence.store import SessionStore
from app.season.free_agents import free_agents
from app.season.power import build_team_sims, matchup_odds, power_rankings
from app.season.results import week_results
from app.sources.espn_league import EspnMatchup, EspnMatchupSide, EspnStatLine

N_START = 3


@pytest.fixture(scope="module")
def snap():
    return generate_demo_snapshot(n_players=120)


@pytest.fixture
def state(tmp_path, snap):
    store = SessionStore(tmp_path / "p.sqlite")
    cfg = demo_league_config(user_pick=1, n_managers=3).model_copy(
        update={"starting_slots": ["G", "F", "UTIL"], "bench_slots": 2, "ir_slots": 1, "draft_type": "linear"}
    )
    sid = store.create_session(cfg, name="power")
    # linear draft, best-first: m01 picks 1,4,7,.. and m03 picks 3,6,9,.. (demo ids are rank-ordered)
    ranked = [p.player_id for p in snap.players]
    i = 0
    while not store.state(sid).is_complete:
        cp = store.state(sid).current_pick
        store.append(
            sid, EventType.pick_committed, {"player_id": ranked[i], "overall": cp.overall, "manager_id": cp.manager_id}
        )
        i += 1
    st = store.state(sid)
    store.close()
    return st


def healthy(snap):
    return {p.player_id: {"injury_status": "ACTIVE", "percent_owned": None, "fetched_at": None} for p in snap.players}


def test_power_rankings_deterministic_and_ranked(snap, state):
    a = power_rankings(snap, state, seed=7, n_scenarios=300)
    b = power_rankings(snap, state, seed=7, n_scenarios=300)
    assert [t.expected_cats for t in a] == [t.expected_cats for t in b]
    assert [t.rank for t in a] == [1, 2, 3]
    assert a[0].expected_cats >= a[1].expected_cats >= a[2].expected_cats
    assert next(t for t in a if t.manager_id == "m01").is_user is True
    assert (
        next(t for t in a if t.manager_id == "m01").expected_cats
        > next(t for t in a if t.manager_id == "m03").expected_cats
    )
    n_cats = len(state.league.categories)
    for t in a:
        assert set(t.cat_win_prob) == {c.key for c in state.league.categories} == set(t.z)
        assert abs(sum(t.cat_win_prob.values()) - t.expected_cats) < 0.05 * n_cats
        assert t.n_players == 5 and t.n_ir == 0
    assert power_rankings(snap, state, seed=8, n_scenarios=300)[0].expected_cats != a[0].expected_cats


def test_power_excludes_ir_from_starters(snap, state):
    roster = state.current_roster("m01")
    top = max(roster, key=lambda p: snap.per_game[snap.index[p], PRIM_IDX["MIN"]])
    sims = build_team_sims(snap, state, ir_player_ids=frozenset({top}))
    me = next(t for t in sims if t.manager_id == "m01")
    assert snap.index[top] in me.roster_idx and snap.index[top] not in me.counted_idx
    assert len(me.counted_idx) == N_START
    with_ir = power_rankings(snap, state, seed=7, ir_player_ids=frozenset({top}), n_scenarios=300)
    without = power_rankings(snap, state, seed=7, n_scenarios=300)
    assert next(t for t in with_ir if t.manager_id == "m01").n_ir == 1
    assert (
        next(t for t in with_ir if t.manager_id == "m01").expected_cats
        < next(t for t in without if t.manager_id == "m01").expected_cats
    )


def test_power_ignores_unknown_player(snap, state):
    from app.draft.events import Event, apply

    ev = Event(
        99,
        EventType.roster_changed,
        {"moves": [{"manager_id": "m02", "added": ["espn:999999"], "dropped": [], "source_ref": "espn:roster-diff"}]},
        "k",
        "now",
        "espn",
    )
    st2 = apply(state, ev)
    sims = build_team_sims(snap, st2, frozenset())
    m2 = next(t for t in sims if t.manager_id == "m02")
    assert len(m2.roster_idx) == 5  # the placeholder is owned but not simulated
    assert power_rankings(snap, st2, seed=7, n_scenarios=200)[0].rank == 1


def schedule_frame(teams: list[str], games: dict[str, int]) -> pd.DataFrame:
    rows = []
    gid = 1
    for t, n in games.items():
        for k in range(n):
            rows.append(
                {"game_id": gid, "date_utc": f"2026-10-2{k % 6}T23:00:00+00:00", "home_team": t, "away_team": "ZZZ"}
            )
            gid += 1
    return pd.DataFrame(rows)


def test_matchup_odds_symmetric(snap, state):
    odds = matchup_odds(
        snap,
        state,
        "m01",
        "m03",
        period=1,
        seed=3,
        schedule=None,
        status=healthy(snap),
        ir_player_ids=frozenset(),
        n_scenarios=400,
    )
    assert abs(odds.p_win_a + odds.p_tie + odds.p_win_b - 1.0) < 1e-9
    assert odds.expected_a > odds.expected_b  # m01 picked first in every round of a linear draft
    flipped = matchup_odds(
        snap,
        state,
        "m03",
        "m01",
        period=1,
        seed=3,
        schedule=None,
        status=healthy(snap),
        ir_player_ids=frozenset(),
        n_scenarios=400,
    )
    assert flipped.p_win_a == odds.p_win_b and flipped.p_win_b == odds.p_win_a and flipped.expected_a == odds.expected_b
    assert set(odds.cat_p_a) == {c.key for c in state.league.categories}
    assert all(0.0 <= v <= 1.0 for v in odds.cat_p_a.values())
    assert odds.modal_score[0] + odds.modal_score[1] == len(state.league.categories)


def test_matchup_odds_without_schedule_falls_back(snap, state):
    odds = matchup_odds(
        snap,
        state,
        "m01",
        "m02",
        period=1,
        seed=3,
        schedule=None,
        status=healthy(snap),
        ir_player_ids=frozenset(),
        n_scenarios=100,
    )
    assert any("season-average" in n for n in odds.notes)


def test_matchup_odds_out_player_zero_games(snap, state):
    roster = state.current_roster("m01")
    star = max(roster, key=lambda p: snap.per_game[snap.index[p], PRIM_IDX["MIN"]])
    teams = sorted({p.team for p in snap.players if p.team})
    sched = schedule_frame(teams, {t: 4 for t in teams})
    base = matchup_odds(
        snap,
        state,
        "m01",
        "m02",
        period=1,
        seed=3,
        schedule=sched,
        status=healthy(snap),
        ir_player_ids=frozenset(),
        n_scenarios=400,
    )
    assert not any("season-average" in n for n in base.notes) and base.games_a > 0
    out = dict(healthy(snap))
    out[star] = {"injury_status": "OUT", "percent_owned": None, "fetched_at": None}
    hurt = matchup_odds(
        snap,
        state,
        "m01",
        "m02",
        period=1,
        seed=3,
        schedule=sched,
        status=out,
        ir_player_ids=frozenset(),
        n_scenarios=400,
    )
    assert hurt.expected_a < base.expected_a and hurt.games_a < base.games_a
    assert any("OUT" in n for n in hurt.notes)


def test_free_agents_exclude_owned_and_pick_best_drop(snap, state):
    status = healthy(snap)
    fas = free_agents(snap, state, status, ir_player_ids=frozenset(), limit=20)
    assert len(fas) == 20
    assert not {f.player_id for f in fas} & state.owned_player_ids
    assert fas[0].score >= fas[1].score
    mins = {p: snap.per_game[snap.index[p], PRIM_IDX["MIN"]] for p in state.current_roster("m01")}
    top_minutes = max(mins, key=mins.get)
    assert all(f.best_drop in state.current_roster("m01") for f in fas)
    assert fas[0].best_drop != top_minutes
    assert fas[0].swap_delta == pytest.approx(fas[0].score - fas[0].drop_value, abs=1e-9)
    # OUT players sort last and carry a flag
    out_status = dict(status)
    out_status[fas[0].player_id] = {"injury_status": "OUT", "percent_owned": 3.0, "fetched_at": None}
    again = free_agents(snap, state, out_status, ir_player_ids=frozenset(), limit=500)
    last = again[-1]
    assert last.player_id == fas[0].player_id and "out" in last.flags and last.percent_owned == 3.0
    assert fas[0].player_id not in {
        f.player_id for f in free_agents(snap, state, out_status, ir_player_ids=frozenset(), limit=20)
    }
    # filters
    guards = free_agents(snap, state, status, ir_player_ids=frozenset(), limit=10, position="PG")
    assert guards and all("PG" in snap.players[snap.index[f.player_id]].eligible_positions for f in guards)
    name = snap.players[snap.index[fas[1].player_id]].name
    hit = free_agents(snap, state, status, ir_player_ids=frozenset(), limit=10, q=name.split()[-1].lower())
    assert any(f.player_id == fas[1].player_id for f in hit)


def test_week_results_from_scorebystat(state):
    def side(tid, pts, reb, fgm, fga, ftm, fta, res):
        by = {
            0: EspnStatLine(pts, res["PTS"]),
            6: EspnStatLine(reb, res["REB"]),
            13: EspnStatLine(fgm, None),
            14: EspnStatLine(fga, None),
            15: EspnStatLine(ftm, None),
            16: EspnStatLine(fta, None),
            19: EspnStatLine(fgm / fga if fga else 0.0, res["FG_PCT"]),
            20: EspnStatLine(ftm / fta if fta else 0.0, res["FT_PCT"]),
            3: EspnStatLine(50, "TIE"),
            2: EspnStatLine(10, "TIE"),
            1: EspnStatLine(5, "TIE"),
            17: EspnStatLine(20, "TIE"),
            11: EspnStatLine(30, "TIE"),
        }
        return EspnMatchupSide(tid, by)

    home = side(1, 400, 150, 150, 300, 80, 100, {"PTS": "WIN", "REB": "LOSS", "FG_PCT": "WIN", "FT_PCT": "LOSS"})
    away = side(2, 380, 160, 140, 300, 90, 100, {"PTS": "LOSS", "REB": "WIN", "FG_PCT": "LOSS", "FT_PCT": "WIN"})
    m = EspnMatchup(5, 2, home, away, "UNDECIDED")
    bye = EspnMatchup(
        6, 2, side(3, 0, 0, 0, 0, 0, 0, {"PTS": None, "REB": None, "FG_PCT": None, "FT_PCT": None}), None, "UNDECIDED"
    )
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class L:
        matchups: tuple

        def matchups_for(self, period):
            return tuple(x for x in self.matchups if x.period == period)

    res = week_results(L((m, bye)), 2, {1: "m01", 2: "m02", 3: "m03"}, state.league.categories)
    assert len(res) == 2
    r = next(x for x in res if x.away is not None)
    assert r.home.manager_id == "m01" and r.away.manager_id == "m02"
    assert r.home.values["PTS"] == 400 and r.home.values["FG_PCT"] == pytest.approx(0.5)
    assert r.home.results["PTS"] == "WIN" and r.home.results["AST"] == "TIE"
    n_cats = len(state.league.categories)
    assert r.home.cats_won == 2 + 0.5 * (n_cats - 4) and r.away.cats_won == 2 + 0.5 * (n_cats - 4)
    b = next(x for x in res if x.away is None)
    assert b.home.manager_id == "m03" and b.home.values["FG_PCT"] is None and b.home.cats_won == 0.0
