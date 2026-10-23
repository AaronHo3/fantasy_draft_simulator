"""Team performers: ESPN applied box scores per matchup period -> contribution and over-expectation rankings."""

from __future__ import annotations

from app.sources.espn_league import parse_boxscore


def boxscore_payload():
    """Two teams, one matchup period, applied stats keyed by ESPN stat id (42 = games, 40 = minutes)."""

    def entry(pid, name, slot, stats):
        return {
            "playerId": pid,
            "lineupSlotId": slot,
            "playerPoolEntry": {"player": {"id": pid, "fullName": name, "stats": [{"id": "05null", "stats": stats}]}},
        }

    star = {
        "42": 3,
        "40": 105,
        "0": 90,
        "6": 24,
        "3": 15,
        "2": 3,
        "1": 2,
        "11": 9,
        "17": 9,
        "18": 24,
        "13": 33,
        "14": 66,
        "15": 15,
        "16": 18,
    }
    role = {
        "42": 3,
        "40": 60,
        "0": 36,
        "6": 18,
        "3": 3,
        "2": 6,
        "1": 3,
        "11": 3,
        "17": 3,
        "18": 6,
        "13": 15,
        "14": 27,
        "15": 3,
        "16": 3,
    }
    dnp = {
        "42": 0,
        "40": 0,
        "0": 0,
        "6": 0,
        "3": 0,
        "2": 0,
        "1": 0,
        "11": 0,
        "17": 0,
        "18": 0,
        "13": 0,
        "14": 0,
        "15": 0,
        "16": 0,
    }
    return {
        "scoringPeriodId": 3,
        "schedule": [
            {
                "id": 1,
                "matchupPeriodId": 1,
                "winner": "UNDECIDED",
                "home": {
                    "teamId": 1,
                    "rosterForMatchupPeriod": {
                        "entries": [
                            entry(101, "Star Player", 0, star),
                            entry(102, "Role Player", 11, role),
                            entry(103, "Bench Guy", 12, dnp),
                        ]
                    },
                },
                "away": {"teamId": 2, "rosterForMatchupPeriod": {"entries": [entry(201, "Other Star", 0, star)]}},
            },
            {
                "id": 2,
                "matchupPeriodId": 1,
                "winner": "UNDECIDED",
                "home": {"teamId": 3, "rosterForMatchupPeriod": {"entries": []}},
            },
            {
                "id": 9,
                "matchupPeriodId": 2,
                "home": {"teamId": 1, "totalPoints": 0.0},
                "away": {"teamId": 3, "totalPoints": 0.0},
            },
        ],
    }


def test_parse_boxscore_yields_applied_stats_per_team_for_the_period():
    rows = parse_boxscore(boxscore_payload(), period=1)
    assert set(rows) == {1, 2, 3}
    star = next(r for r in rows[1] if r.espn_player_id == 101)
    assert star.name == "Star Player" and star.games == 3 and star.minutes == 105 and star.stats["PTS"] == 90
    assert (
        star.stats["FGM"] == 33
        and star.stats["FGA"] == 66
        and star.stats["FTM"] == 15
        and star.stats["FTA"] == 18
        and star.stats["TOV"] == 9
    )
    bench = next(r for r in rows[1] if r.espn_player_id == 103)
    assert bench.games == 0 and bench.lineup_slot_id == 12
    assert rows[3] == []
    assert parse_boxscore(boxscore_payload(), period=2) == {}  # not played yet: no applied rosters


def test_period_scoring_period_id():
    from app.season.weeks import first_scoring_period_id

    assert first_scoring_period_id("2026-27", 1) == 1
    assert first_scoring_period_id("2026-27", 2) == 7  # 2026-10-26 is day 7 from opening night
    assert first_scoring_period_id("2026-27", 18) == 119


def test_store_period_player_stats_roundtrip(tmp_path):
    from app.league.config import demo_league_config
    from app.persistence.store import SessionStore

    store = SessionStore(tmp_path / "p.sqlite")
    sid = store.create_session(demo_league_config(), name="p")
    rec = {
        "period": 1,
        "manager_id": "m01",
        "player_id": "demo:0001",
        "espn_id": 101,
        "name": "Star",
        "games": 3,
        "minutes": 105.0,
        "stats": {"PTS": 90.0},
        "source": "espn_boxscore",
        "fetched_at": "t1",
    }
    store.upsert_period_player_stats(sid, [rec])
    store.upsert_period_player_stats(sid, [{**rec, "games": 4, "fetched_at": "t2"}, {**rec, "period": 2, "games": 1}])
    rows = store.period_player_stats(sid)
    assert len(rows) == 2 and rows[0]["games"] == 4 and rows[0]["fetched_at"] == "t2" and rows[1]["period"] == 2
    assert store.period_player_stats(sid, period=2)[0]["games"] == 1
    assert store.periods_with_stats(sid) == [1, 2]
    store.delete_session(sid)
    assert store.period_player_stats(sid) == []
