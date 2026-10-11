from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from app.league.config import eligible_positions_from_espn_slots, espn_season_id
from app.sources import espn_public
from app.sources.base import SchemaError
from app.sources.espn_public import (
    PLAYERS_COLUMNS,
    SCHEDULE_COLUMNS,
    parse_player,
    parse_players,
    parse_schedule,
    players_filter,
    split_totals,
    stat_split_id,
)
from tests.sources.conftest import ESPN_FIXTURES, raw_from


def test_season_id_mapping_and_filter():
    assert espn_season_id("2026-27") == 2027
    flt = players_filter(2027)["players"]
    assert flt["filterActive"] == {"value": True} and flt["limit"] == 2000
    assert flt["filterStatsForTopScoringPeriodIds"]["additionalValue"] == ["002027", "102027", "002026"]
    assert flt["sortDraftRanks"]["value"] == "STANDARD"


def test_stat_split_ids():
    assert stat_split_id(2027, "projection") == "102027"
    assert stat_split_id(2027, "actual") == "002027"
    assert stat_split_id(2026, "actual") == "002026"


def test_split_totals_selects_split_and_ignores_empty():
    stats = [
        {"id": "002027", "stats": {}},
        {"id": "102027", "stats": {"0": 346.0, "42": 65, "40": 825.5, "19": 0.421}},
        {"id": "05401810055", "stats": {"0": 9}},
    ]
    proj = split_totals(stats, "102027")
    assert proj is not None
    assert proj["pts"] == 346.0 and proj["gp"] == 65.0 and proj["min"] == 825.5
    assert proj["reb"] is None and "19" not in proj and not any(k.endswith("pct") for k in proj)
    assert split_totals(stats, "002027") is None  # empty stats dict == absent
    assert split_totals(stats, "002026") is None and split_totals(None, "102027") is None


@pytest.mark.parametrize(
    ("slots", "expected"),
    [
        ([3, 4, 6, 8, 9, 10, 11, 12, 13], {"PF", "C"}),
        ([1, 5, 7, 8, 11, 12, 13], {"SG"}),
        ([0, 1, 5, 7, 8, 11, 12, 13], {"PG", "SG"}),
        ([11, 12, 13], set()),
        ([], set()),
    ],
)
def test_slot_to_primitive_positions(slots, expected):
    assert eligible_positions_from_espn_slots(slots) == frozenset(expected)
    rec = parse_player({"id": 1, "fullName": "X", "active": True, "eligibleSlots": slots}, 2027)
    assert json.loads(rec["eligible_positions_json"]) == sorted(expected)
    assert json.loads(rec["eligible_slots_json"]) == slots


@pytest.mark.parametrize(
    ("pos_id", "expected"), [(1, "PG"), (2, "SG"), (3, "SF"), (4, "PF"), (5, "C"), (0, None), (-1, None), (None, None)]
)
def test_default_position_id_is_one_indexed(pos_id, expected):
    rec = parse_player({"id": 1, "fullName": "X", "defaultPositionId": pos_id}, 2027)
    assert rec["primary_position"] == expected


def test_parse_players_keeps_active_only_and_schema(espn_players_payload):
    before = copy.deepcopy(espn_players_payload)
    df = parse_players(espn_players_payload, 2027, fetched_at="2026-10-09T00:00:00+00:00")
    assert espn_players_payload == before
    assert list(df.columns) == list(PLAYERS_COLUMNS)
    assert len(df) == 22 and len(espn_players_payload) == 24 and df["active"].all()
    assert "Norvel Pelle" not in set(df["name"])
    assert df["espn_id"].dtype == "int64" and df["espn_team_id"].dtype == "int64"
    assert df["injured"].dtype == "bool" and str(df["rank_standard"].dtype) == "Int64"
    assert (df["source"] == "espn_public").all() and (df["season_id"] == 2027).all()
    assert set(df["team"].dropna()) == {"BOS", "PHI", "PHX"}  # ESPN 20/21 -> PHI/PHX


def test_parse_players_values(espn_players_payload):
    df = parse_players(espn_players_payload, 2027).set_index("name")
    hansen_like = df.loc["Jayson Tatum"]
    assert hansen_like["primary_position"] == "PF" and hansen_like["team"] == "BOS"
    assert json.loads(hansen_like["eligible_positions_json"]) == ["PF", "SF"]
    assert hansen_like["injury_status"] == "DAY_TO_DAY" and hansen_like["rank_standard"] == 9
    assert hansen_like["adp"] == pytest.approx(9.24)
    assert hansen_like["adp_asof"] == "2026-10-10T00:30:30+00:00"
    assert hansen_like["proj_gp"] == 70.0 and hansen_like["proj_pts"] == 1869.0
    assert hansen_like["prev_pts"] == 348.0 and hansen_like["proj_min"] == 2534.0
    dante = df.loc["N'Faly Dante"]
    assert pd.isna(dante["team"]) and dante["espn_team_id"] == 0 and dante["injury_status"] == "OUT"
    assert pd.isna(dante["proj_gp"]) and pd.isna(dante["proj_pts"])  # no projection split
    assert df["proj_gp"].notna().sum() == 21 and df["prev_gp"].notna().sum() == 22
    assert not any(c.endswith("pct") for c in df.columns)


def test_parse_players_empty_and_bad_shape():
    empty = parse_players([], 2027)
    assert list(empty.columns) == list(PLAYERS_COLUMNS) and empty.empty
    with pytest.raises(SchemaError):
        parse_players({"players": []}, 2027)
    with pytest.raises(SchemaError):
        parse_players([{"active": True, "name": "no id"}], 2027)


def test_parse_schedule(espn_schedule_payload):
    before = copy.deepcopy(espn_schedule_payload)
    df = parse_schedule(espn_schedule_payload, 2027, fetched_at="2026-10-09T00:00:00+00:00")
    assert espn_schedule_payload == before
    assert list(df.columns) == list(SCHEDULE_COLUMNS)
    assert df["game_id"].is_unique and len(df) == 6  # each game listed under both teams once
    assert df["scoring_period_id"].dtype == "int64" and df["scoring_period_id"].min() == 1
    assert set(df["home_team"]) | set(df["away_team"]) >= {"BOS", "PHI", "PHX"}
    assert "PHL" not in set(df["home_team"]) and "PHO" not in set(df["away_team"])
    first = df.iloc[0]
    assert first["game_id"] == 401909088 and first["date_utc"] == "2026-10-20T19:00:00+00:00"
    assert first["home_team"] == "DET" and first["away_team"] == "BOS"
    assert df["date_utc"].is_monotonic_increasing
    with pytest.raises(SchemaError):
        parse_schedule({"settings": {}}, 2027)


def test_fetchers_compose_without_network(monkeypatch):
    monkeypatch.setattr(
        espn_public, "fetch_players_raw", lambda season_id, client=None: raw_from(ESPN_FIXTURES / "players_2027.json")
    )
    monkeypatch.setattr(
        espn_public, "fetch_schedule_raw", lambda season_id, client=None: raw_from(ESPN_FIXTURES / "schedule_2027.json")
    )
    assert len(espn_public.fetch_players(2027)) == 22
    assert len(espn_public.fetch_schedule(2027)) == 6


def test_real_fetchers_are_offline_in_tests():
    with pytest.raises(Exception, match="network access is disabled|attempts failed"):
        espn_public.fetch_schedule_raw(2027)
