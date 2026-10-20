"""Link / sync / season endpoints with the ESPN fetchers replaced by in-memory fakes."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from app.sources.espn_league import (
    EspnLeague,
    EspnMatchup,
    EspnMatchupSide,
    EspnRosterEntry,
    EspnSettings,
    EspnStatLine,
    EspnTeam,
    EspnTransaction,
    EspnTransactionItem,
    LeagueAccessError,
)

LEAGUE_ID = 2075231076
ESPN_BASE_ID = 100000


def espn_id_of(player_id: str) -> int:
    return ESPN_BASE_ID + int(player_id.split(":")[1])


def demo(n: int) -> str:
    return f"demo:{n:04d}"


def make_settings(**over) -> EspnSettings:
    base = dict(
        name="Fake League",
        scoring_type="H2H_CATEGORY",
        stat_ids=(0, 1, 2, 3, 6, 11, 17, 19, 20),
        lineup_slot_counts={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 11: 3, 12: 3, 13: 1},
        position_limits={5: 4},
        lineup_lock_type="WEEKLY",
        matchup_period_count=19,
        playoff_team_count=4,
        current_matchup_period=1,
        scoring_period_id=1,
    )
    base.update(over)
    return EspnSettings(**base)


def make_team(
    team_id: int, owner: str, player_ids: list[str], names: dict[str, str], ir: str | None = None
) -> EspnTeam:
    roster = tuple(
        EspnRosterEntry(espn_id_of(p), names.get(p, p), 13 if p == ir else 11, "ACTIVE", "DRAFT", None)
        for p in player_ids
    )
    return EspnTeam(team_id, f"T{team_id}", f"Team {team_id}", (f"{{o{team_id}}}",), owner, roster, 0, 0, 0, None, None)


def make_league(teams: list[EspnTeam], fetched_at: str, transactions=(), matchups=(), settings=None) -> EspnLeague:
    return EspnLeague(
        LEAGUE_ID, 2027, settings or make_settings(), tuple(teams), tuple(matchups), tuple(transactions), fetched_at
    )


def pair(matchup_id: int, period: int, home: int, away: int | None, home_stats=None, away_stats=None) -> EspnMatchup:
    def side(tid, stats):
        return EspnMatchupSide(tid, {k: EspnStatLine(v, r) for k, (v, r) in (stats or {}).items()})

    return EspnMatchup(
        matchup_id, period, side(home, home_stats), None if away is None else side(away, away_stats), "UNDECIDED"
    )


@pytest.fixture
def complete_session(client):
    """Demo league trimmed to 3 managers x 4 roster spots, fully drafted."""
    from app.league.config import demo_league_config

    cfg = demo_league_config(user_pick=1, n_managers=3).model_copy(
        update={"starting_slots": ["G", "F", "UTIL"], "bench_slots": 1, "ir_slots": 1}
    )
    r = client.post("/api/sessions", json={"league": cfg.model_dump(mode="json")})
    sid = r.json()["id"]
    ctx = client.app.state.ctx
    snap = ctx.registry.get(ctx.registry.default_id())
    # give every demo player an ESPN id so the fake league can reference them
    patched = replace(snap, players=tuple(replace(p, espn_id=espn_id_of(p.player_id)) for p in snap.players))
    ctx.registry.register(patched)
    st = client.get(f"/api/sessions/{sid}/state").json()
    pid = 1
    while st["current_pick"] is not None:
        cp = st["current_pick"]
        st = client.post(
            f"/api/sessions/{sid}/events",
            json={
                "type": "pick_committed",
                "payload": {"player_id": demo(pid), "overall": cp["overall"], "manager_id": cp["manager_id"]},
            },
        ).json()["state"]
        pid += 1
    assert st["is_complete"]
    return sid


def league_from_state(
    client, sid, fetched_at="2026-10-19T04:00:00+00:00", add=None, drop=None, matchups=(), transactions=()
):
    st = client.get(f"/api/sessions/{sid}/state").json()
    ctx = client.app.state.ctx
    snap = ctx.registry.get(ctx.registry.default_id())
    names = {p.player_id: p.name for p in snap.players}
    teams = []
    for i, m in enumerate(st["league"]["managers"], start=1):
        roster = list(st["current_rosters"][m["id"]])
        if add and add[0] == m["id"]:
            roster.append(add[1])
        if drop and drop[0] == m["id"]:
            roster.remove(drop[1])
        teams.append(make_team(i, f"Owner {i}", roster, names, ir=roster[-1] if i == 2 else None))
    return make_league(teams, fetched_at, transactions=transactions, matchups=matchups)


def install_fakes(client, league: EspnLeague | Exception, players: pd.DataFrame | Exception | None = None):
    ctx = client.app.state.ctx
    calls = {"league": 0, "players": 0}

    def fake_league(league_id: int, season_id: int):
        calls["league"] += 1
        if isinstance(league, Exception):
            raise league
        assert league_id == LEAGUE_ID and season_id == 2027
        return league, {"id": league_id}

    def fake_players(season_id: int) -> pd.DataFrame:
        calls["players"] += 1
        if isinstance(players, Exception):
            raise players
        return (
            players
            if players is not None
            else pd.DataFrame(columns=["espn_id", "injury_status", "percent_owned", "team", "fetched_at"])
        )

    ctx.espn_fetch_league = fake_league
    ctx.espn_fetch_players = fake_players
    return calls


def link(client, sid):
    preview = client.post(f"/api/sessions/{sid}/espn/link", json={"league_id": LEAGUE_ID}).json()
    mapping = {m["manager_id"]: m["team_id"] for m in preview["mapping"]}
    r = client.post(f"/api/sessions/{sid}/espn/link/apply", json={"league_id": LEAGUE_ID, "mapping": mapping})
    assert r.status_code == 200, r.text
    return mapping


# --- link ---------------------------------------------------------------------------------------


def test_link_preview_maps_teams(client, complete_session):
    sid = complete_session
    install_fakes(client, league_from_state(client, sid))
    r = client.post(f"/api/sessions/{sid}/espn/link", json={"league_id": LEAGUE_ID})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["league_name"] == "Fake League"
    assert {m["manager_id"]: m["team_id"] for m in body["mapping"]} == {"m01": 1, "m02": 2, "m03": 3}
    assert all(m["confidence"] == "high" for m in body["mapping"])
    assert body["unmatched_managers"] == [] and body["unmatched_teams"] == []
    assert any(
        "starting slots" in w for w in body["settings_warnings"]
    )  # fake league has a full lineup, the session 3 slots
    assert len(body["teams"]) == 3 and body["teams"][1]["n_players"] == 4
    # the preview writes nothing
    assert client.get(f"/api/sessions/{sid}/state").json()["league"]["espn_league_id"] is None


def test_link_rejects_bad_league_id(client, complete_session):
    r = client.post(f"/api/sessions/{complete_session}/espn/link", json={"league_id": 0})
    assert r.status_code == 422


def test_link_apply_sets_fields(client, complete_session):
    sid = complete_session
    install_fakes(client, league_from_state(client, sid))
    mapping = link(client, sid)
    league = client.get(f"/api/sessions/{sid}/state").json()["league"]
    assert league["espn_league_id"] == LEAGUE_ID and league["espn_team_ids"] == mapping
    assert league["espn_linked_at"] is not None


# --- sync ---------------------------------------------------------------------------------------


def test_sync_not_linked_409(client, complete_session):
    install_fakes(client, league_from_state(client, complete_session))
    r = client.post(f"/api/sessions/{complete_session}/espn/sync", json={})
    assert r.status_code == 409 and r.json()["code"] == "not_linked"


def test_sync_private_league_409(client, complete_session):
    sid = complete_session
    install_fakes(client, league_from_state(client, sid))
    link(client, sid)
    install_fakes(client, LeagueAccessError("private"))
    r = client.post(f"/api/sessions/{sid}/espn/sync", json={})
    assert r.status_code == 409 and r.json()["code"] == "league_private"
    assert "Viewable to Public" in r.json()["message"]


def test_sync_applies_roster_changes_and_is_idempotent(client, complete_session, tmp_path):
    sid = complete_session
    install_fakes(client, league_from_state(client, sid))
    link(client, sid)
    before = client.get(f"/api/sessions/{sid}/state").json()
    dropped = before["current_rosters"]["m02"][0]
    live = pd.DataFrame(
        {
            "espn_id": [espn_id_of(demo(500))],
            "injury_status": ["OUT"],
            "percent_owned": [12.5],
            "team": ["BOS"],
            "fetched_at": ["2026-10-19T04:00:00+00:00"],
        }
    )
    tx = EspnTransaction(
        "tx-1",
        "FREEAGENT",
        "EXECUTED",
        2,
        "2026-10-19T03:00:00+00:00",
        1,
        (
            EspnTransactionItem("ADD", espn_id_of(demo(500)), 0, 2),
            EspnTransactionItem("DROP", espn_id_of(dropped), 2, 0),
        ),
    )
    calls = install_fakes(
        client, league_from_state(client, sid, add=("m02", demo(500)), drop=("m02", dropped), transactions=(tx,)), live
    )
    r = client.post(f"/api/sessions/{sid}/espn/sync", json={"expected_revision": before["last_seq"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] == "ESPN sync: 1 adds, 1 drops across 1 teams; 0 unknown players"
    assert body["changes"] == [
        {
            "manager_id": "m02",
            "team_id": 2,
            "added": [demo(500)],
            "dropped": [dropped],
            "source_refs": ["espn:tx-1", "espn:tx-1"],
        }
    ]
    assert demo(500) in body["state"]["current_rosters"]["m02"] and dropped not in body["state"]["owned_player_ids"]
    assert body["state"]["last_seq"] == before["last_seq"] + 1
    assert body["ids"]["draft_revision"] == body["state"]["last_seq"]
    assert calls == {"league": 1, "players": 1}
    ctx = client.app.state.ctx
    rec = ctx.store.get_sync(sid)
    assert (
        rec["league_id"] == LEAGUE_ID
        and rec["fetched_at"] == "2026-10-19T04:00:00+00:00"
        and rec["summary"] == body["summary"]
    )
    assert (ctx.settings.live_dir / str(LEAGUE_ID) / "players.parquet").exists()
    assert ctx.live_status(LEAGUE_ID).iloc[0]["injury_status"] == "OUT"
    # second sync with the same ESPN state: no events, cache refreshed
    install_fakes(client, league_from_state(client, sid, fetched_at="2026-10-19T05:00:00+00:00"))
    r2 = client.post(f"/api/sessions/{sid}/espn/sync", json={})
    assert r2.status_code == 200 and r2.json()["changes"] == []
    assert r2.json()["state"]["last_seq"] == body["state"]["last_seq"]
    assert ctx.store.get_sync(sid)["fetched_at"] == "2026-10-19T05:00:00+00:00"


def test_sync_conflict_on_stale_revision(client, complete_session):
    sid = complete_session
    install_fakes(client, league_from_state(client, sid))
    link(client, sid)
    install_fakes(client, league_from_state(client, sid, add=("m03", demo(501))))
    r = client.post(f"/api/sessions/{sid}/espn/sync", json={"expected_revision": 1})
    assert r.status_code == 409 and r.json()["code"] == "revision_conflict"
    assert demo(501) not in client.get(f"/api/sessions/{sid}/state").json()["owned_player_ids"]


def test_sync_players_feed_failure_is_a_warning(client, complete_session):
    sid = complete_session
    install_fakes(client, league_from_state(client, sid))
    link(client, sid)
    install_fakes(
        client, league_from_state(client, sid, fetched_at="2026-10-19T06:00:00+00:00"), RuntimeError("espn down")
    )
    r = client.post(f"/api/sessions/{sid}/espn/sync", json={})
    assert r.status_code == 200 and any("player status" in w for w in r.json()["warnings"])
