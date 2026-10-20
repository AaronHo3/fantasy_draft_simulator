"""Pure parsers over the public ESPN league payload (fixture trimmed from league 2075231076, 2026-10-19)."""

import json
from pathlib import Path

import httpx
import pytest

from app.league.config import LineupMode, demo_league_config
from app.sources.espn_league import (
    LeagueAccessError,
    fetch_league_raw,
    league_url,
    parse_league,
    settings_diff,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "espn_league_small.json"


@pytest.fixture(scope="module")
def league():
    payload = json.loads(FIXTURE.read_text())
    return parse_league(payload, league_id=2075231076, season_id=2027, fetched_at="2026-10-19T04:00:00+00:00")


def test_parse_settings(league):
    s = league.settings
    assert s.name == "1000Thieves"
    assert s.scoring_type == "H2H_CATEGORY"
    assert s.stat_ids == (0, 1, 2, 3, 6, 17, 19, 20)
    assert s.lineup_slot_counts[11] == 3
    assert s.position_limits[5] == 4
    assert s.lineup_lock_type == "INDIVIDUAL_GAME"
    assert s.matchup_period_count == 19
    assert s.current_matchup_period == 1
    assert league.league_id == 2075231076 and league.season_id == 2027


def test_parse_teams_and_rosters(league):
    assert len(league.teams) == 3
    george = league.team(7)
    assert len(george.roster) == 14
    assert sum(1 for e in george.roster if e.lineup_slot_id == 13) == 1
    assert george.owner_name == "George Hu"
    assert "Cade Cunningham" in {e.name for e in george.roster}
    assert george.wins == 0 and george.losses == 0


def test_parse_matchups_bye(league):
    p1 = league.matchups_for(1)
    byes = [m for m in p1 if m.away is None]
    assert len(byes) == 1 and byes[0].home.team_id == 1
    for m in p1:
        if m.away is not None:
            assert m.home.team_id != m.away.team_id
            assert m.home.by_stat[0].result in {"WIN", "LOSS", "TIE", None}
    assert all(m.period == 2 for m in league.matchups_for(2))


def test_parse_transactions_roster_moves(league):
    moves = [t for t in league.transactions if t.is_roster_move]
    assert len(moves) == 8  # George: 4 adds + 3 drops; Kevin: 1 waiver add
    assert all(t.status == "EXECUTED" for t in moves)
    assert sorted(t.team_id for t in moves) == [5, 7, 7, 7, 7, 7, 7, 7]
    others = [t for t in league.transactions if not t.is_roster_move]
    assert {t.status for t in others} >= {"CANCELED", "FAILED_ROSTERLIMIT"}
    assert any(t.kind == "DRAFT" for t in others)
    assert all(t.proposed_at.endswith("+00:00") for t in league.transactions)


def test_fetch_private_league_raises(monkeypatch):
    calls = []

    def fake_get(self, url, params=None, headers=None):
        calls.append(url)
        return httpx.Response(401, json={"messages": ["not authorized"]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    with pytest.raises(LeagueAccessError):
        fetch_league_raw(2075231076, 2027)
    assert len(calls) == 1  # a private league is not retried
    assert league_url(2075231076, 2027).endswith("/seasons/2027/segments/0/leagues/2075231076")


def test_settings_diff_flags_daily_vs_weekly(league):
    cfg = demo_league_config(n_managers=13)
    cfg = cfg.model_copy(
        update={"categories": [c for c in cfg.categories if c.key != "TOV"], "lineup_mode": LineupMode.weekly}
    )
    lines = settings_diff(league.settings, cfg)
    assert any("daily" in ln for ln in lines)
    assert not any("categor" in ln for ln in lines)
    daily = cfg.model_copy(update={"lineup_mode": LineupMode.daily})
    assert settings_diff(league.settings, daily) == []
