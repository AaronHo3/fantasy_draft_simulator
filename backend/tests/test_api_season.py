"""Link / sync / season endpoints with the ESPN fetchers replaced by in-memory fakes."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from app.draft.events import EventType
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


def raw_from_league(league: EspnLeague) -> dict:
    """ESPN-shaped JSON for the fake league so the cached payload re-parses after a restart."""
    s = league.settings
    return {
        "id": league.league_id,
        "seasonId": league.season_id,
        "scoringPeriodId": s.scoring_period_id,
        "status": {"currentMatchupPeriod": s.current_matchup_period},
        "settings": {
            "name": s.name,
            "scoringSettings": {"scoringType": s.scoring_type, "scoringItems": [{"statId": i} for i in s.stat_ids]},
            "rosterSettings": {
                "lineupSlotCounts": {str(k): v for k, v in s.lineup_slot_counts.items()},
                "positionLimits": {str(k): v for k, v in s.position_limits.items()},
                "lineupLocktimeType": s.lineup_lock_type,
            },
            "scheduleSettings": {
                "matchupPeriodCount": s.matchup_period_count,
                "playoffTeamCount": s.playoff_team_count,
            },
        },
        "members": [
            {"id": t.owner_ids[0], "firstName": t.owner_name.split()[0], "lastName": " ".join(t.owner_name.split()[1:])}
            for t in league.teams
        ],
        "teams": [
            {
                "id": t.team_id,
                "abbrev": t.abbrev,
                "name": t.name,
                "owners": list(t.owner_ids),
                "primaryOwner": t.owner_ids[0],
                "record": {"overall": {"wins": t.wins, "losses": t.losses, "ties": t.ties}},
                "roster": {
                    "entries": [
                        {
                            "playerId": e.espn_player_id,
                            "lineupSlotId": e.lineup_slot_id,
                            "injuryStatus": e.injury_status,
                            "acquisitionType": e.acquisition_type,
                            "playerPoolEntry": {"player": {"id": e.espn_player_id, "fullName": e.name}},
                        }
                        for e in t.roster
                    ]
                },
            }
            for t in league.teams
        ],
        "schedule": [
            {
                "id": m.matchup_id,
                "matchupPeriodId": m.period,
                "winner": m.winner,
                "home": {
                    "teamId": m.home.team_id,
                    "cumulativeScore": {
                        "scoreByStat": {
                            str(k): {"score": v.score, "result": v.result} for k, v in m.home.by_stat.items()
                        }
                    },
                },
                **(
                    {
                        "away": {
                            "teamId": m.away.team_id,
                            "cumulativeScore": {
                                "scoreByStat": {
                                    str(k): {"score": v.score, "result": v.result} for k, v in m.away.by_stat.items()
                                }
                            },
                        }
                    }
                    if m.away
                    else {}
                ),
            }
            for m in league.matchups
        ],
        "transactions": [
            {
                "id": tx.transaction_id,
                "type": tx.kind,
                "status": tx.status,
                "teamId": tx.team_id,
                "proposedDate": 1792286818992,
                "scoringPeriodId": tx.scoring_period_id,
                "items": [
                    {
                        "type": it.kind,
                        "playerId": it.espn_player_id,
                        "fromTeamId": it.from_team_id,
                        "toTeamId": it.to_team_id,
                    }
                    for it in tx.items
                ],
            }
            for tx in league.transactions
        ],
    }


def install_fakes(client, league: EspnLeague | Exception, players: pd.DataFrame | Exception | None = None):
    ctx = client.app.state.ctx
    calls = {"league": 0, "players": 0}

    def fake_league(league_id: int, season_id: int):
        calls["league"] += 1
        if isinstance(league, Exception):
            raise league
        assert league_id == LEAGUE_ID and season_id == 2027
        return league, raw_from_league(league)

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
    assert "Viewable to Public" in r.json()["message"] and "cookie" not in r.json()["message"].lower()


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


# --- season read endpoints ----------------------------------------------------------------------


def stats(pts, reb, fgm, fga, ftm, fta, res_pts, res_reb):
    return {
        0: (pts, res_pts),
        6: (reb, res_reb),
        13: (fgm, None),
        14: (fga, None),
        15: (ftm, None),
        16: (fta, None),
        3: (40, "TIE"),
        2: (8, "TIE"),
        1: (4, "TIE"),
        17: (15, "TIE"),
        11: (20, "TIE"),
        19: (fgm / fga, "WIN"),
        20: (ftm / fta, "LOSS"),
    }


def week1(user_home=True):
    """Period 1: team 1 (user) vs team 2, team 3 on a bye."""
    a, b = (1, 2) if user_home else (2, 1)
    return (
        pair(
            1,
            1,
            a,
            b,
            stats(400, 150, 150, 300, 80, 100, "WIN", "LOSS"),
            stats(380, 160, 140, 300, 90, 100, "LOSS", "WIN"),
        ),
        pair(2, 1, 3, None),
        pair(3, 2, 2, 3),
        pair(4, 2, 1, None),
    )


def linked_and_synced(client, sid, matchups):
    install_fakes(client, league_from_state(client, sid, matchups=matchups))
    link(client, sid)
    r = client.post(f"/api/sessions/{sid}/espn/sync", json={})
    assert r.status_code == 200, r.text
    return r.json()


def test_overview_unlinked_still_returns_power(client, complete_session):
    r = client.get(f"/api/sessions/{complete_session}/season/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked"] is False and body["matchups"] == [] and body["user_matchup"] is None
    assert [p["rank"] for p in body["power"]] == [1, 2, 3]
    assert body["ids"]["snapshot_id"] and body["synced_at"] is None


def test_overview_linked_has_matchups_and_user_matchup(client, complete_session):
    sid = complete_session
    linked_and_synced(client, sid, week1())
    r = client.get(f"/api/sessions/{sid}/season/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (
        body["linked"] is True
        and body["league_name"] == "Fake League"
        and body["synced_at"] == "2026-10-19T04:00:00+00:00"
    )
    assert body["current_period"] == 1
    assert len(body["matchups"]) == 2
    um = body["user_matchup"]
    assert um["home_manager_id"] == "m01" and um["away_manager_id"] == "m02"
    odds = um["odds"]
    assert abs(odds["p_win_a"] + odds["p_tie"] + odds["p_win_b"] - 1) < 1e-9
    assert set(odds["cat_p_a"]) == {c["key"] for c in body["league_categories"]}
    bye = next(m for m in body["matchups"] if m["away_manager_id"] is None)
    assert bye["home_manager_id"] == "m03" and bye["odds"] is None
    assert body["movement"] == {}  # first sync: nothing to compare with
    assert body["power"][0]["rank"] == 1 and len(body["power"]) == 3
    # a period selector re-pairs from ESPN's schedule
    r2 = client.get(f"/api/sessions/{sid}/season/overview", params={"period": 2})
    um2 = r2.json()["user_matchup"]
    assert um2["home_manager_id"] == "m01" and um2["away_manager_id"] is None


def test_overview_user_bye(client, complete_session):
    sid = complete_session
    linked_and_synced(client, sid, (pair(1, 1, 2, 3), pair(2, 1, 1, None)))
    body = client.get(f"/api/sessions/{sid}/season/overview").json()
    assert body["user_matchup"]["away_manager_id"] is None and body["user_matchup"]["odds"] is None
    other = next(m for m in body["matchups"] if m["away_manager_id"] is not None)
    assert other["odds"]["manager_a"] == "m02" and other["odds"]["manager_b"] == "m03"


def test_overview_movement_after_second_sync(client, complete_session):
    sid = complete_session
    linked_and_synced(client, sid, week1())
    st = client.get(f"/api/sessions/{sid}/state").json()
    weakest = client.get(f"/api/sessions/{sid}/season/overview").json()["power"][-1]["manager_id"]
    # the weakest team adds the best free agent and drops its worst player
    fa = client.get(f"/api/sessions/{sid}/season/free-agents", params={"limit": 1}).json()["items"][0]["player"][
        "player_id"
    ]
    drop = st["current_rosters"][weakest][-1]
    install_fakes(
        client,
        league_from_state(
            client,
            sid,
            fetched_at="2026-10-20T04:00:00+00:00",
            add=(weakest, fa),
            drop=(weakest, drop),
            matchups=week1(),
        ),
    )
    assert client.post(f"/api/sessions/{sid}/espn/sync", json={}).status_code == 200
    body = client.get(f"/api/sessions/{sid}/season/overview").json()
    assert set(body["movement"]) == {"m01", "m02", "m03"}
    assert sum(body["movement"].values()) == 0


def test_matchup_endpoint(client, complete_session):
    sid = complete_session
    linked_and_synced(client, sid, week1())
    r = client.get(f"/api/sessions/{sid}/season/matchup", params={"period": 1, "team_a": "m02", "team_b": "m03"})
    assert r.status_code == 200, r.text
    assert r.json()["odds"]["manager_a"] == "m02" and r.json()["ids"]["draft_revision"] > 0
    assert (
        client.get(
            f"/api/sessions/{sid}/season/matchup", params={"period": 1, "team_a": "m02", "team_b": "zz"}
        ).status_code
        == 422
    )


def test_free_agents_endpoint_excludes_owned(client, complete_session):
    sid = complete_session
    linked_and_synced(client, sid, week1())
    st = client.get(f"/api/sessions/{sid}/state").json()
    r = client.get(f"/api/sessions/{sid}/season/free-agents", params={"limit": 15})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 15 and body["synced_at"] == "2026-10-19T04:00:00+00:00"
    ids = {it["player"]["player_id"] for it in body["items"]}
    assert not ids & set(st["owned_player_ids"])
    first = body["items"][0]
    assert first["best_drop"]["player_id"] in st["current_rosters"]["m01"]
    assert (
        first["player"]["name"]
        and "z" in first
        and first["swap_delta"] == pytest.approx(first["score"] - first["drop_value"], abs=1e-6)
    )
    q = client.get(f"/api/sessions/{sid}/season/free-agents", params={"q": first["player"]["name"].split()[-1]}).json()
    assert any(it["player"]["player_id"] == first["player"]["player_id"] for it in q["items"])


def test_results_endpoint_from_cached_payload(client, complete_session):
    sid = complete_session
    linked_and_synced(client, sid, week1())
    r = client.get(f"/api/sessions/{sid}/season/results", params={"period": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == 1 and len(body["results"]) == 2
    game = next(x for x in body["results"] if x["away"] is not None)
    assert (
        game["home"]["manager_id"] == "m01"
        and game["home"]["values"]["PTS"] == 400
        and game["home"]["results"]["PTS"] == "WIN"
    )
    assert game["home"]["values"]["FG_PCT"] == pytest.approx(0.5)
    assert game["home"]["cats_won"] == game["away"]["cats_won"]
    assert len(body["projected"]) == 2 and body["projected"][0]["period"] == 1
    # the parsed league survives a process restart through the cached raw payload
    ctx = client.app.state.ctx
    ctx.leagues.clear()
    assert client.get(f"/api/sessions/{sid}/season/results", params={"period": 1}).status_code == 200


def test_results_unlinked_409(client, complete_session):
    r = client.get(f"/api/sessions/{complete_session}/season/results", params={"period": 1})
    assert r.status_code == 409 and r.json()["code"] == "not_linked"


# --- CLI ------------------------------------------------------------------------------------------


def test_cli_link_and_sync(client, complete_session, monkeypatch, capsys):
    from app import cli

    sid = complete_session
    install_fakes(client, league_from_state(client, sid, matchups=week1()))
    ctx = client.app.state.ctx
    monkeypatch.setattr(cli, "build_context", lambda _settings: ctx)
    assert cli.main(["espn-link", sid, str(LEAGUE_ID)]) == 0
    out = capsys.readouterr().out
    assert "m01" in out and "Team 1" in out and "preview only" in out
    assert client.get(f"/api/sessions/{sid}/state").json()["league"]["espn_league_id"] is None
    assert cli.main(["espn-link", sid, str(LEAGUE_ID), "--apply", "--map", "m01=1"]) == 0
    assert client.get(f"/api/sessions/{sid}/state").json()["league"]["espn_league_id"] == LEAGUE_ID
    assert cli.main(["espn-sync", sid]) == 0
    assert "ESPN sync:" in capsys.readouterr().out
    assert cli.main(["season", sid]) == 0
    out = capsys.readouterr().out
    assert "period 1" in out and "m01" in out or "Team 1" in out


def test_sync_race_is_rejected_not_double_applied(client, complete_session):
    """A plan built from one state must not be applied over a state that moved on (auto-refresh vs manual)."""
    sid = complete_session
    install_fakes(client, league_from_state(client, sid))
    link(client, sid)
    st = client.get(f"/api/sessions/{sid}/state").json()
    victim = st["current_rosters"]["m03"][0]
    league = league_from_state(
        client, sid, fetched_at="2026-10-19T07:00:00+00:00", add=("m03", demo(600)), drop=("m03", victim)
    )
    ctx = client.app.state.ctx
    calls = {"n": 0}

    def racing_fetch(league_id, season_id):
        calls["n"] += 1
        if calls["n"] == 1:  # another sync lands while this one is talking to ESPN
            ctx.store.append(
                sid,
                EventType.roster_changed,
                {
                    "moves": [
                        {"manager_id": "m03", "added": [demo(600)], "dropped": [victim], "source_ref": "espn:other"}
                    ]
                },
                source="espn",
            )
        return league, raw_from_league(league)

    ctx.espn_fetch_league = racing_fetch
    r = client.post(f"/api/sessions/{sid}/espn/sync", json={})
    assert r.status_code == 409 and r.json()["code"] == "revision_conflict"
    after = client.get(f"/api/sessions/{sid}/state").json()
    assert after["current_rosters"]["m03"].count(demo(600)) == 1
    # the retry sees the already-applied state: nothing to do
    r2 = client.post(f"/api/sessions/{sid}/espn/sync", json={})
    assert r2.status_code == 200 and r2.json()["changes"] == []


def test_overview_movement_survives_a_no_change_sync(client, complete_session):
    sid = complete_session
    linked_and_synced(client, sid, week1())
    st = client.get(f"/api/sessions/{sid}/state").json()
    weakest = client.get(f"/api/sessions/{sid}/season/overview").json()["power"][-1]["manager_id"]
    fa = client.get(f"/api/sessions/{sid}/season/free-agents", params={"limit": 1}).json()["items"][0]["player"][
        "player_id"
    ]
    install_fakes(
        client,
        league_from_state(
            client,
            sid,
            fetched_at="2026-10-20T04:00:00+00:00",
            add=(weakest, fa),
            drop=(weakest, st["current_rosters"][weakest][-1]),
            matchups=week1(),
        ),
    )
    assert client.post(f"/api/sessions/{sid}/espn/sync", json={}).status_code == 200
    moved = client.get(f"/api/sessions/{sid}/season/overview").json()["movement"]
    install_fakes(client, league_from_state(client, sid, fetched_at="2026-10-20T05:00:00+00:00", matchups=week1()))
    assert client.post(f"/api/sessions/{sid}/espn/sync", json={}).status_code == 200
    assert client.get(f"/api/sessions/{sid}/season/overview").json()["movement"] == moved


# --- predictions log ----------------------------------------------------------------------------


def decided_week1():
    m = week1()
    return (replace(m[0], winner="HOME"), *m[1:])


def test_prediction_store_roundtrip(tmp_path):
    from app.league.config import demo_league_config
    from app.persistence.store import SessionStore

    store = SessionStore(tmp_path / "p.sqlite")
    sid = store.create_session(demo_league_config(), name="p")
    assert store.predictions(sid) == []
    rec = {
        "period": 1,
        "home_manager_id": "m01",
        "away_manager_id": "m02",
        "predicted_winner": "m01",
        "p_winner": 0.7,
        "locked": False,
    }
    store.upsert_prediction(sid, 1, "m01", rec)
    store.upsert_prediction(sid, 1, "m01", {**rec, "p_winner": 0.8})
    store.upsert_prediction(sid, 2, "m01", {**rec, "period": 2})
    rows = store.predictions(sid)
    assert [r["period"] for r in rows] == [1, 2] and rows[0]["p_winner"] == 0.8
    store.delete_session(sid)
    assert store.predictions(sid) == []


def test_predictions_recorded_on_sync_and_locked_once_the_week_starts(client, complete_session, monkeypatch):
    from datetime import date

    from app.season import service as season

    sid = complete_session
    monkeypatch.setattr(season, "_today", lambda: date(2026, 10, 19))  # before period 1 starts
    linked_and_synced(client, sid, week1())
    r = client.get(f"/api/sessions/{sid}/season/predictions")
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(p for p in body["predictions"] if p["period"] == 1 and p["home_manager_id"] == "m01")
    assert row["away_manager_id"] == "m02" and row["locked"] is False
    odds = client.get(f"/api/sessions/{sid}/season/overview").json()["user_matchup"]["odds"]
    expected_winner = "m01" if odds["p_win_a"] >= odds["p_win_b"] else "m02"
    assert row["predicted_winner"] == expected_winner and row["actual_winner"] is None and row["correct"] is None
    assert body["summary"]["n_decided"] == 0
    # the overview above rewrote the (still open) row; the frozen copy must match the last pre-week write
    row = next(
        p
        for p in client.get(f"/api/sessions/{sid}/season/predictions").json()["predictions"]
        if p["period"] == 1 and p["home_manager_id"] == "m01"
    )
    # the week starts: the prediction freezes even though rosters change afterwards
    monkeypatch.setattr(season, "_today", lambda: date(2026, 10, 21))
    st = client.get(f"/api/sessions/{sid}/state").json()
    install_fakes(client, league_from_state(client, sid, fetched_at="2026-10-21T04:00:00+00:00", matchups=week1()))
    assert client.post(f"/api/sessions/{sid}/espn/sync", json={}).status_code == 200
    locked = next(
        p
        for p in client.get(f"/api/sessions/{sid}/season/predictions").json()["predictions"]
        if p["period"] == 1 and p["home_manager_id"] == "m01"
    )
    assert locked["locked"] is True and locked["p_winner"] == row["p_winner"]
    fa = client.get(f"/api/sessions/{sid}/season/free-agents", params={"limit": 1}).json()["items"][0]["player"][
        "player_id"
    ]
    install_fakes(
        client,
        league_from_state(
            client,
            sid,
            fetched_at="2026-10-22T04:00:00+00:00",
            add=("m02", fa),
            drop=("m02", st["current_rosters"]["m02"][0]),
            matchups=week1(),
        ),
    )
    assert client.post(f"/api/sessions/{sid}/espn/sync", json={}).status_code == 200
    again = next(
        p
        for p in client.get(f"/api/sessions/{sid}/season/predictions").json()["predictions"]
        if p["period"] == 1 and p["home_manager_id"] == "m01"
    )
    assert again["p_winner"] == row["p_winner"] and again["predicted_at"] == row["predicted_at"]


def test_predictions_scored_against_espn_results(client, complete_session, monkeypatch):
    from datetime import date

    from app.season import service as season

    sid = complete_session
    monkeypatch.setattr(season, "_today", lambda: date(2026, 10, 19))
    linked_and_synced(client, sid, decided_week1())
    body = client.get(f"/api/sessions/{sid}/season/predictions").json()
    row = next(p for p in body["predictions"] if p["period"] == 1 and p["home_manager_id"] == "m01")
    assert row["actual_winner"] == "m01" and row["correct"] == (row["predicted_winner"] == "m01")
    assert row["actual_cats"] == {"m01": row["actual_cats"]["m01"], "m02": row["actual_cats"]["m02"]}
    s = body["summary"]
    assert s["n_decided"] == 1 and s["n_correct"] == (1 if row["correct"] else 0)
    assert s["hit_rate"] == pytest.approx(s["n_correct"] / 1) and 0 <= s["brier"] <= 1
    bye = next(p for p in body["predictions"] if p["period"] == 1 and p["away_manager_id"] is None)
    assert bye["predicted_winner"] is None and bye["actual_winner"] is None


def test_cached_league_reloads_when_a_newer_payload_was_written(client, complete_session):
    """A CLI sync writes league.json from another process; the app must not keep serving its older copy."""
    from app.season import service as season

    sid = complete_session
    first = league_from_state(client, sid, fetched_at="2026-10-19T04:00:00+00:00", matchups=week1())
    install_fakes(client, first)
    link(client, sid)
    assert client.post(f"/api/sessions/{sid}/espn/sync", json={}).status_code == 200
    ctx = client.app.state.ctx
    assert season.cached_league(ctx, LEAGUE_ID, "2026-27").fetched_at == "2026-10-19T04:00:00+00:00"
    # another process syncs later and writes a newer payload to disk
    newer = league_from_state(client, sid, fetched_at="2026-10-23T07:43:00+00:00", matchups=week1())
    path = ctx.settings.live_dir / str(LEAGUE_ID) / "league.json"
    import json as _json

    path.write_text(_json.dumps({"fetched_at": newer.fetched_at, "payload": raw_from_league(newer)}))
    assert season.cached_league(ctx, LEAGUE_ID, "2026-27").fetched_at == "2026-10-23T07:43:00+00:00"
    # and the overview reports the newer sync time even though this process did not run it
    assert client.get(f"/api/sessions/{sid}/season/overview").json()["synced_at"] == "2026-10-23T07:43:00+00:00"
