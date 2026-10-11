from __future__ import annotations

import copy
import datetime as dt

import pandas as pd
import pytest

from app.sources import nba_stats
from app.sources.base import SchemaError
from app.sources.nba_stats import (
    GAME_LOGS_COLUMNS,
    PLAYERS_COLUMNS,
    SEASON_TOTALS_COLUMNS,
    normalize_game_logs,
    normalize_players,
    normalize_season_totals,
    result_set_frame,
    season_type_slug,
    validate_season,
    validate_season_type,
)
from tests.sources.conftest import NBA_FIXTURES, raw_from

COUNTS = ["fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "tov", "stl", "blk", "pts"]


def test_normalize_players_schema_and_values(players_payload):
    before = copy.deepcopy(players_payload)
    df = normalize_players(players_payload, "2026-27", fetched_at="2026-10-09T00:00:00+00:00")
    assert players_payload == before  # pure
    assert list(df.columns) == list(PLAYERS_COLUMNS)
    assert len(df) == 22 and df["nba_id"].dtype == "int64" and df["nba_id"].is_unique
    assert df["from_year"].dtype == "int64" and df["to_year"].dtype == "int64"
    assert df["roster_status"].dtype == "int64" and str(df["team_id"].dtype) == "Int64"
    assert set(df["team"].dropna()) == {"BOS", "PHI", "PHX"}  # NBA tricodes, not ESPN PHL/PHO
    assert (df["source"] == "nba_api").all() and (df["season"] == "2026-27").all()
    assert (df["fetched_at"] == "2026-10-09T00:00:00+00:00").all()
    assert df["season_type"].isna().all()
    tatum = df[df["name"] == "Jayson Tatum"].iloc[0]
    assert tatum["nba_id"] == 1628369 and tatum["team"] == "BOS" and tatum["team_id"] == 1610612738


def test_normalize_players_no_team_becomes_missing(players_payload):
    rs = players_payload["resultSets"][0]
    h = rs["headers"]
    row = list(rs["rowSet"][0])
    row[h.index("TEAM_ID")] = 0
    row[h.index("TEAM_ABBREVIATION")] = ""
    payload = {**players_payload, "resultSets": [{**rs, "rowSet": [row]}]}
    df = normalize_players(payload, "2026-27")
    assert pd.isna(df["team"].iloc[0]) and pd.isna(df["team_id"].iloc[0])


def test_normalize_season_totals_schema_and_traded_flag(totals_payload):
    df = normalize_season_totals(totals_payload, "2025-26", "Regular Season", fetched_at="2026-10-09T00:00:00+00:00")
    assert list(df.columns) == list(SEASON_TOTALS_COLUMNS)
    assert len(df) == 22
    for c in COUNTS + ["gp", "team_count"]:
        assert df[c].dtype == "int64", c
    assert df["min"].dtype == "float64" and df["age"].dtype == "float64"
    assert not any(c.endswith("_pct") for c in df.columns)  # percentages never stored
    traded = df[df["team_count"] > 1]
    assert set(traded["name"]) == {"Anfernee Simons", "Luke Kennard", "Amir Coffey"}
    assert (df[df["name"] == "Jayson Tatum"]["team_count"] == 1).all()
    coffey = traded[traded["name"] == "Amir Coffey"].iloc[0]
    assert coffey["team"] == "PHX" and coffey["gp"] == 46 and coffey["pts"] == 149
    assert (df["season_type"] == "Regular Season").all() and (df["season"] == "2025-26").all()


def test_normalize_game_logs_schema_home_and_dates(game_logs_payload):
    df = normalize_game_logs(game_logs_payload, "2025-26", "Regular Season", fetched_at="2026-10-09T00:00:00+00:00")
    assert list(df.columns) == list(GAME_LOGS_COLUMNS)
    assert len(df) == 12 and df["home"].dtype == "bool"
    assert df["game_id"].str.len().eq(10).all() and df["game_id"].iloc[0].startswith("002")
    assert all(isinstance(d, dt.date) for d in df["game_date"])
    home = df[df["matchup"].str.contains("vs.", regex=False)]
    away = df[df["matchup"].str.contains("@", regex=False)]
    assert home["home"].all() and not away["home"].any() and len(home) == len(away) == 6
    for c in COUNTS:
        assert df[c].dtype == "int64", c
    row = df.iloc[0]
    assert row["name"] == "Baylor Scheierman" and row["team"] == "BOS"
    assert row["game_date"] == dt.date(2025, 10, 29) and row["min"] == pytest.approx(10.2333, abs=1e-3)


def test_result_set_frame_validates_shape():
    with pytest.raises(SchemaError):
        result_set_frame({"resource": "x"})
    with pytest.raises(SchemaError, match="missing columns"):
        result_set_frame({"resultSets": [{"headers": ["A"], "rowSet": []}]}, ("A", "B"))
    assert result_set_frame({"resultSets": [{"headers": ["A"], "rowSet": []}]}, ("A",)).empty


def test_season_validation_and_slug():
    assert validate_season("2025-26") == "2025-26"
    with pytest.raises(ValueError):
        validate_season("2025")
    with pytest.raises(ValueError):
        validate_season("2025-27")
    assert validate_season_type("Playoffs") == "Playoffs"
    with pytest.raises(ValueError):
        validate_season_type("Pre Season")
    assert season_type_slug("Regular Season") == "regular_season"


def test_fetchers_compose_raw_and_normalize_without_network(monkeypatch):
    monkeypatch.setattr(
        nba_stats, "fetch_players_raw", lambda season: raw_from(NBA_FIXTURES / "commonallplayers_2026-27.json")
    )
    monkeypatch.setattr(
        nba_stats,
        "fetch_season_totals_raw",
        lambda season, season_type="Regular Season": raw_from(NBA_FIXTURES / "leaguedashplayerstats_2025-26.json"),
    )
    monkeypatch.setattr(
        nba_stats,
        "fetch_game_logs_raw",
        lambda season, season_type="Regular Season": raw_from(
            NBA_FIXTURES / "playergamelogs_2025-26_regular_season.json"
        ),
    )
    assert len(nba_stats.fetch_active_players("2026-27")) == 22
    totals = nba_stats.fetch_season_totals("2025-26")
    assert len(totals) == 22 and (totals["season_type"] == "Regular Season").all()
    logs = nba_stats.fetch_game_logs("2025-26", "Playoffs")
    assert len(logs) == 12 and (logs["season_type"] == "Playoffs").all()


def test_real_fetcher_is_offline_in_tests():
    with pytest.raises(Exception, match="network access is disabled|attempts failed"):
        nba_stats.fetch_players_raw("2026-27")
