"""Team mapping by roster overlap and the pure sync planner, against the trimmed ESPN fixture."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.demo.generate import generate_demo_snapshot
from app.draft.events import Event, EventType, apply
from app.league.config import demo_league_config
from app.persistence.store import SessionStore
from app.season.link import match_teams
from app.season.sync import canonical_id, plan_sync
from app.sources.espn_league import EspnRosterEntry, parse_league

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "espn_league_small.json"
GEORGE_ADDS = (4278129, 4431767, 6430, 4277956)
GEORGE_DROPS = (4601023, 2528210, 4431785)
# session manager -> ESPN team, deliberately not in positional order
MAPPING = {"m01": 9, "m02": 7, "m03": 1}


@pytest.fixture(scope="module")
def espn():
    return parse_league(json.loads(FIXTURE.read_text()), 2075231076, 2027, "2026-10-19T04:00:00+00:00")


@pytest.fixture(scope="module")
def snap(espn):
    """Demo snapshot whose first players carry the ESPN ids of every rostered or dropped player."""
    base = generate_demo_snapshot(n_players=80)
    espn_ids = sorted({e.espn_player_id for t in espn.teams for e in t.roster} | set(GEORGE_DROPS))
    names = {e.espn_player_id: e.name for t in espn.teams for e in t.roster}
    players = list(base.players)
    for i, eid in enumerate(espn_ids):
        players[i] = replace(players[i], espn_id=eid, name=names.get(eid, f"Dropped {eid}"))
    return replace(base, players=tuple(players))


def by_espn(snap):
    return {p.espn_id: p.player_id for p in snap.players if p.espn_id}


@pytest.fixture
def session(tmp_path, espn, snap):
    """Three managers draft exactly the pre-transaction ESPN rosters (George's drops in, adds out)."""
    store = SessionStore(tmp_path / "s.sqlite")
    cfg = demo_league_config(user_pick=1, n_managers=3)
    sid = store.create_session(cfg, name="link-test")
    ids = by_espn(snap)
    targets = {}
    for m, tid in MAPPING.items():
        roster = [e.espn_player_id for e in espn.team(tid).roster]
        if tid == 7:
            roster = [x for x in roster if x not in GEORGE_ADDS] + list(GEORGE_DROPS)
        targets[m] = [ids[x] for x in roster]
    queues = {m: list(v) for m, v in targets.items()}
    while not store.state(sid).is_complete:
        cp = store.state(sid).current_pick
        pid = queues[cp.manager_id].pop(0)
        store.append(
            sid, EventType.pick_committed, {"player_id": pid, "overall": cp.overall, "manager_id": cp.manager_id}
        )
    yield store, sid
    store.close()


def test_match_teams_by_overlap_with_renamed_owner(session, espn, snap):
    store, sid = session
    mapping = match_teams(store.state(sid), espn, snap)
    assert mapping.as_dict() == MAPPING
    conf = {m.manager_id: m.confidence for m in mapping.matches}
    assert conf["m01"] == "high" and conf["m03"] == "high" and conf["m02"] in {"high", "medium"}
    assert mapping.unmatched_managers == () and mapping.unmatched_teams == ()


def test_match_teams_override_wins(session, espn, snap):
    store, sid = session
    mapping = match_teams(store.state(sid), espn, snap, overrides={"m01": 1})
    d = mapping.as_dict()
    assert d["m01"] == 1 and d["m03"] == 9 and d["m02"] == 7
    assert any("m01" in w for w in mapping.warnings)


def test_plan_sync_first_sync_writes_league_updated(session, espn, snap):
    store, sid = session
    plan = plan_sync(store.state(sid), espn, snap, MAPPING)
    assert plan.events[0][0] == EventType.league_updated
    league = plan.events[0][1]["league"]
    assert league["espn_league_id"] == 2075231076 and league["espn_team_ids"] == MAPPING
    assert plan.events[0][2] == "espn-link:2075231076:2026-10-19T04:00:00+00:00"


def test_plan_sync_adds_drops_attributed_to_transactions(session, espn, snap):
    store, sid = session
    ids = by_espn(snap)
    plan = plan_sync(store.state(sid), espn, snap, MAPPING)
    diffs = {d.manager_id: d for d in plan.diffs}
    assert set(diffs) == {"m02"}
    d = diffs["m02"]
    assert sorted(d.added) == sorted(ids[x] for x in GEORGE_ADDS)
    assert sorted(d.dropped) == sorted(ids[x] for x in GEORGE_DROPS)
    assert len(d.source_refs) == 7 and all(r.startswith("espn:") and r != "espn:roster-diff" for r in d.source_refs)
    rc = [e for e in plan.events if e[0] == EventType.roster_changed]
    assert len(rc) == 1 and rc[0][2] == "espn-sync:2075231076:2026-10-19T04:00:00+00:00"
    assert rc[0][1]["moves"][0]["manager_id"] == "m02"
    assert plan.summary == "ESPN sync: 4 adds, 3 drops across 1 teams; 0 unknown players"
    assert plan.unknown_players == ()


def test_plan_sync_no_changes_has_no_events(session, espn, snap):
    store, sid = session
    first = plan_sync(store.state(sid), espn, snap, MAPPING)
    for t, payload, key in first.events:
        store.append(sid, t, payload, key, source="espn")
    again = plan_sync(store.state(sid), espn, snap, MAPPING)
    assert again.events == () and again.diffs == ()
    assert again.summary == "ESPN sync: 0 adds, 0 drops across 0 teams; 0 unknown players"


def test_plan_sync_trade_in_one_event(session, espn, snap):
    store, sid = session
    first = plan_sync(store.state(sid), espn, snap, MAPPING)
    for t, payload, key in first.events:
        store.append(sid, t, payload, key, source="espn")
    t1, t9 = espn.team(1), espn.team(9)
    swapped = replace(
        espn,
        teams=tuple(
            replace(t, roster=(t9.roster[0], *t.roster[1:]))
            if t.team_id == 1
            else replace(t, roster=(t1.roster[0], *t.roster[1:]))
            if t.team_id == 9
            else t
            for t in espn.teams
        ),
        fetched_at="2026-10-20T04:00:00+00:00",
    )
    plan = plan_sync(store.state(sid), swapped, snap, MAPPING)
    rc = [e for e in plan.events if e[0] == EventType.roster_changed]
    assert len(rc) == 1 and len(rc[0][1]["moves"]) == 2
    assert all("espn:roster-diff" in d.source_refs for d in plan.diffs)
    st = apply(store.state(sid), Event(99, EventType.roster_changed, rc[0][1], rc[0][2], "now", "espn"))
    ids = by_espn(snap)
    assert ids[t9.roster[0].espn_player_id] in st.current_roster("m03")
    assert ids[t1.roster[0].espn_player_id] in st.current_roster("m01")


def test_plan_sync_unknown_player_is_owned_placeholder(session, espn, snap):
    store, sid = session
    first = plan_sync(store.state(sid), espn, snap, MAPPING)
    for t, payload, key in first.events:
        store.append(sid, t, payload, key, source="espn")
    callup = EspnRosterEntry(999999, "Two Way Guy", 12, "ACTIVE", "ADD", None)
    t9 = espn.team(9)
    league = replace(
        espn,
        teams=tuple(replace(t, roster=(*t.roster[1:], callup)) if t.team_id == 9 else t for t in espn.teams),
        fetched_at="2026-10-21T04:00:00+00:00",
    )
    assert canonical_id(snap, 999999, "Two Way Guy") == "espn:999999"
    plan = plan_sync(store.state(sid), league, snap, MAPPING)
    assert plan.unknown_players == ((999999, "Two Way Guy"),)
    d = plan.diffs[0]
    assert (
        d.manager_id == "m01"
        and d.added == ("espn:999999",)
        and d.dropped == (by_espn(snap)[t9.roster[0].espn_player_id],)
    )
    assert any("999999" in w or "Two Way Guy" in w for w in plan.warnings)
