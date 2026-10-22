"""Week-by-week actual-vs-projection tracking for a roster, and hot-start screening of free agents."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from app.demo.generate import generate_demo_snapshot
from app.draft.events import EventType
from app.engine.categories import PRIM_IDX
from app.league.config import demo_league_config
from app.persistence.store import SessionStore
from app.season.performance import append_tracker, free_agent_hot_starts, performance_table, player_week_lines


@pytest.fixture(scope="module")
def snap():
    base = generate_demo_snapshot(n_players=60)
    # give every demo player an NBA id so game logs can be joined
    return replace(base, players=tuple(replace(p, nba_id=9000 + i) for i, p in enumerate(base.players)))


@pytest.fixture
def state(tmp_path, snap):
    store = SessionStore(tmp_path / "perf.sqlite")
    cfg = demo_league_config(user_pick=1, n_managers=3).model_copy(
        update={"starting_slots": ["G", "F", "UTIL"], "bench_slots": 1, "ir_slots": 1}
    )
    sid = store.create_session(cfg, name="perf")
    ids = [p.player_id for p in snap.players]
    i = 0
    while not store.state(sid).is_complete:
        cp = store.state(sid).current_pick
        store.append(
            sid, EventType.pick_committed, {"player_id": ids[i], "overall": cp.overall, "manager_id": cp.manager_id}
        )
        i += 1
    st = store.state(sid)
    store.close()
    return st


def logs_for(snap, state, period_days):
    """Two games for the user's first player (one double his projection, one at it); one game for the second."""
    mine = state.current_roster("m01")
    rows = []
    for k, pid in enumerate(mine[:2]):
        p = snap.players[snap.index[pid]]
        pg = snap.per_game[snap.index[pid]]
        for g, mult in enumerate([2.0, 1.0] if k == 0 else [1.0]):
            rows.append(
                {
                    "nba_id": p.nba_id,
                    "name": p.name,
                    "game_id": f"g{k}{g}",
                    "game_date": period_days[g],
                    "team": p.team,
                    "min": pg[PRIM_IDX["MIN"]] * mult,
                    "pts": pg[PRIM_IDX["PTS"]] * mult,
                    "reb": pg[PRIM_IDX["REB"]] * mult,
                    "ast": pg[PRIM_IDX["AST"]] * mult,
                    "stl": pg[PRIM_IDX["STL"]] * mult,
                    "blk": pg[PRIM_IDX["BLK"]] * mult,
                    "fg3m": pg[PRIM_IDX["FG3M"]] * mult,
                    "fg3a": pg[PRIM_IDX["FG3A"]] * mult,
                    "fgm": pg[PRIM_IDX["FGM"]] * mult,
                    "fga": pg[PRIM_IDX["FGA"]] * mult,
                    "ftm": pg[PRIM_IDX["FTM"]] * mult,
                    "fta": pg[PRIM_IDX["FTA"]] * mult,
                    "tov": pg[PRIM_IDX["TOV"]] * mult,
                }
            )
    # a free agent with a monster game
    fa = next(p for p in snap.players if p.player_id not in state.owned_player_ids)
    pg = snap.per_game[snap.index[fa.player_id]]
    rows.append(
        {
            "nba_id": fa.nba_id,
            "name": fa.name,
            "game_id": "fa1",
            "game_date": period_days[0],
            "team": fa.team,
            "min": 36.0,
            "pts": pg[PRIM_IDX["PTS"]] * 3,
            "reb": 12,
            "ast": 8,
            "stl": 3,
            "blk": 2,
            "fg3m": 4,
            "fg3a": 8,
            "fgm": 12,
            "fga": 20,
            "ftm": 6,
            "fta": 6,
            "tov": 2,
        }
    )
    return pd.DataFrame(rows), fa


def test_player_week_lines_averages_games_in_the_window(snap, state):
    logs, _ = logs_for(snap, state, [date(2026, 10, 20), date(2026, 10, 21)])
    lines = player_week_lines(logs, date(2026, 10, 20), date(2026, 10, 25))
    first = snap.players[snap.index[state.current_roster("m01")[0]]]
    row = lines.loc[first.nba_id]
    assert row["games"] == 2 and row["pts"] == pytest.approx(
        snap.per_game[snap.index[first.player_id], PRIM_IDX["PTS"]] * 1.5
    )
    assert player_week_lines(logs, date(2026, 11, 2), date(2026, 11, 8)).empty


def test_performance_table_compares_actual_to_projection(snap, state):
    logs, _ = logs_for(snap, state, [date(2026, 10, 20), date(2026, 10, 21)])
    df = performance_table(
        snap, state, logs, period=1, manager_id="m01", window=(date(2026, 10, 20), date(2026, 10, 25))
    )
    mine = state.current_roster("m01")
    assert set(df["player_id"]) == set(mine) and (df["period"] == 1).all()
    first = df[df.player_id == mine[0]].iloc[0]
    assert first["games"] == 2 and first["pts_actual"] == pytest.approx(first["pts_proj"] * 1.5)
    assert first["pts_delta"] == pytest.approx(first["pts_proj"] * 0.5)
    assert first["value_delta"] > 0  # over expectation
    second = df[df.player_id == mine[1]].iloc[0]
    assert second["games"] == 1 and abs(second["value_delta"]) < 1e-6  # exactly on projection
    dnp = df[df.player_id == mine[2]].iloc[0]
    assert dnp["games"] == 0 and pd.isna(dnp["pts_actual"]) and pd.isna(dnp["value_delta"])
    assert "fg_pct_actual" in df.columns and "ft_pct_proj" in df.columns


def test_append_tracker_replaces_the_same_week(tmp_path, snap, state):
    logs, _ = logs_for(snap, state, [date(2026, 10, 20), date(2026, 10, 21)])
    df = performance_table(snap, state, logs, 1, "m01", (date(2026, 10, 20), date(2026, 10, 25)))
    path = tmp_path / "tracker.csv"
    append_tracker(path, df)
    append_tracker(path, df.assign(pts_actual=df.pts_actual + 1))  # re-run of the same week overwrites
    again = performance_table(snap, state, logs, 2, "m01", (date(2026, 10, 26), date(2026, 11, 1)))
    append_tracker(path, again)
    saved = pd.read_csv(path)
    assert sorted(saved["period"].unique()) == [1, 2] and len(saved) == 2 * len(df)
    pid = df["player_id"].iloc[0]
    stored = saved[(saved.period == 1) & (saved.player_id == pid)]["pts_actual"].iloc[0]
    assert stored == pytest.approx(df[df.player_id == pid]["pts_actual"].iloc[0] + 1)


def test_free_agent_hot_starts_ranks_unowned_players_by_actual_production(snap, state):
    logs, fa = logs_for(snap, state, [date(2026, 10, 20), date(2026, 10, 21)])
    status = {p.player_id: {"injury_status": "ACTIVE"} for p in snap.players}
    hot = free_agent_hot_starts(snap, state, logs, status, (date(2026, 10, 20), date(2026, 10, 25)), limit=5)
    assert hot.iloc[0]["player_id"] == fa.player_id and hot.iloc[0]["games"] == 1
    assert not set(hot["player_id"]) & state.owned_player_ids
    assert hot.iloc[0]["value_actual"] > hot.iloc[0]["value_proj"]
