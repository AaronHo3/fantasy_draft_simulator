"""stats.nba.com adapter via ``nba_api`` (its default headers are required on this network).

Three league-wide endpoints, one request per season each. Fetching and normalizing are separate:
``fetch_*_raw`` return :class:`RawResponse`, ``normalize_*`` are pure functions over the parsed
JSON, and ``fetch_*`` compose the two.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pandas as pd

from app.league.config import espn_season_id
from app.sources.base import RawResponse, SchemaError, utc_now_iso, with_retries
from app.sources.teams import normalize_tricode

log = logging.getLogger(__name__)

SOURCE = "nba_api"
NBA_TIMEOUT_S = 60
SEASON_TYPES: tuple[str, ...] = ("Regular Season", "Playoffs")
ENDPOINT_PLAYERS = "commonallplayers"
ENDPOINT_SEASON_TOTALS = "leaguedashplayerstats"
ENDPOINT_GAME_LOGS = "playergamelogs"

# Source column -> normalized column for counting primitives (shared by totals and game logs).
COUNT_COLUMNS: dict[str, str] = {
    "FGM": "fgm",
    "FGA": "fga",
    "FG3M": "fg3m",
    "FG3A": "fg3a",
    "FTM": "ftm",
    "FTA": "fta",
    "OREB": "oreb",
    "DREB": "dreb",
    "REB": "reb",
    "AST": "ast",
    "TOV": "tov",
    "STL": "stl",
    "BLK": "blk",
    "PTS": "pts",
}
PROVENANCE_COLUMNS: tuple[str, ...] = ("source", "fetched_at", "season", "season_type")

PLAYERS_COLUMNS: tuple[str, ...] = (
    "nba_id",
    "name",
    "team",
    "team_id",
    "from_year",
    "to_year",
    "roster_status",
    *PROVENANCE_COLUMNS,
)
SEASON_TOTALS_COLUMNS: tuple[str, ...] = (
    "nba_id",
    "name",
    "season",
    "season_type",
    "team",
    "team_count",
    "age",
    "gp",
    "min",
    *COUNT_COLUMNS.values(),
    "source",
    "fetched_at",
)
GAME_LOGS_COLUMNS: tuple[str, ...] = (
    "nba_id",
    "name",
    "season",
    "season_type",
    "team",
    "game_id",
    "game_date",
    "matchup",
    "home",
    "min",
    *COUNT_COLUMNS.values(),
    "source",
    "fetched_at",
)


def validate_season(season: str) -> str:
    espn_season_id(season)  # raises ValueError on malformed input such as "2026"
    return season


def validate_season_type(season_type: str) -> str:
    if season_type not in SEASON_TYPES:
        raise ValueError(f"season_type must be one of {SEASON_TYPES}, got {season_type!r}")
    return season_type


def season_type_slug(season_type: str) -> str:
    return season_type.lower().replace(" ", "_")


# --- parsing ---------------------------------------------------------------------------------


def result_set_frame(payload: Any, required: tuple[str, ...] = ()) -> pd.DataFrame:
    """First ``resultSets`` entry of a stats.nba.com payload as a DataFrame with source headers."""
    if not isinstance(payload, dict) or not payload.get("resultSets"):
        raise SchemaError("nba_api payload has no resultSets")
    rs = payload["resultSets"][0]
    headers = rs.get("headers")
    rows = rs.get("rowSet")
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise SchemaError("nba_api resultSet lacks headers/rowSet")
    missing = [c for c in required if c not in headers]
    if missing:
        raise SchemaError(f"nba_api resultSet missing columns {missing}")
    return pd.DataFrame(rows, columns=headers)


def _team_series(abbrevs: pd.Series) -> pd.Series:
    return abbrevs.map(normalize_tricode, na_action="ignore").astype("str")


def _counts(src: pd.DataFrame) -> dict[str, pd.Series]:
    return {dst: src[col].fillna(0).astype("int64") for col, dst in COUNT_COLUMNS.items()}


def normalize_players(payload: Any, season: str, fetched_at: str | None = None) -> pd.DataFrame:
    """commonallplayers -> players table (one row per player on the current universe)."""
    src = result_set_frame(
        payload,
        ("PERSON_ID", "DISPLAY_FIRST_LAST", "TEAM_ID", "TEAM_ABBREVIATION", "FROM_YEAR", "TO_YEAR", "ROSTERSTATUS"),
    )
    team_id = pd.to_numeric(src["TEAM_ID"], errors="coerce").astype("Int64")
    out = pd.DataFrame(
        {
            "nba_id": src["PERSON_ID"].astype("int64"),
            "name": src["DISPLAY_FIRST_LAST"].astype("str"),
            "team": _team_series(src["TEAM_ABBREVIATION"]),
            "team_id": team_id.mask(team_id == 0),
            "from_year": pd.to_numeric(src["FROM_YEAR"]).astype("int64"),
            "to_year": pd.to_numeric(src["TO_YEAR"]).astype("int64"),
            "roster_status": pd.to_numeric(src["ROSTERSTATUS"]).fillna(0).astype("int64"),
        }
    )
    return _with_provenance(out, season, None, fetched_at)[list(PLAYERS_COLUMNS)]


def normalize_season_totals(
    payload: Any,
    season: str,
    season_type: str = "Regular Season",
    fetched_at: str | None = None,
) -> pd.DataFrame:
    """leaguedashplayerstats Totals -> season_totals (one row per player; traded => team_count>1)."""
    src = result_set_frame(
        payload, ("PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP", "MIN", "TEAM_COUNT", *COUNT_COLUMNS)
    )
    out = pd.DataFrame(
        {
            "nba_id": src["PLAYER_ID"].astype("int64"),
            "name": src["PLAYER_NAME"].astype("str"),
            "team": _team_series(src["TEAM_ABBREVIATION"]),
            "team_count": src["TEAM_COUNT"].fillna(1).astype("int64"),
            "age": pd.to_numeric(src["AGE"], errors="coerce").astype("float64"),
            "gp": src["GP"].fillna(0).astype("int64"),
            "min": pd.to_numeric(src["MIN"], errors="coerce").astype("float64"),
            **_counts(src),
        }
    )
    return _with_provenance(out, season, season_type, fetched_at)[list(SEASON_TOTALS_COLUMNS)]


def normalize_game_logs(
    payload: Any,
    season: str,
    season_type: str = "Regular Season",
    fetched_at: str | None = None,
) -> pd.DataFrame:
    """playergamelogs -> game_logs (one row per player-game)."""
    src = result_set_frame(
        payload,
        ("PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_ID", "GAME_DATE", "MATCHUP", "MIN", *COUNT_COLUMNS),
    )
    matchup = src["MATCHUP"].astype("str")
    out = pd.DataFrame(
        {
            "nba_id": src["PLAYER_ID"].astype("int64"),
            "name": src["PLAYER_NAME"].astype("str"),
            "team": _team_series(src["TEAM_ABBREVIATION"]),
            "game_id": src["GAME_ID"].astype("str"),
            "game_date": pd.to_datetime(src["GAME_DATE"]).dt.date,
            "matchup": matchup,
            "home": matchup.str.contains(" vs. ", regex=False).fillna(False).astype("bool"),
            "min": pd.to_numeric(src["MIN"], errors="coerce").astype("float64"),
            **_counts(src),
        }
    )
    return _with_provenance(out, season, season_type, fetched_at)[list(GAME_LOGS_COLUMNS)]


def _with_provenance(
    frame: pd.DataFrame,
    season: str,
    season_type: str | None,
    fetched_at: str | None,
) -> pd.DataFrame:
    return frame.assign(
        source=SOURCE,
        fetched_at=fetched_at or utc_now_iso(),
        season=season,
        season_type=season_type,
    ).astype({"season_type": "str"})


# --- fetching --------------------------------------------------------------------------------


def _call_endpoint(make: Callable[[], Any], params: dict[str, Any]) -> RawResponse:
    """Run an nba_api endpoint constructor with bounded retries and wrap its response."""

    def once() -> RawResponse:
        endpoint = make()
        response = endpoint.nba_response
        body = response.get_json()
        payload = response.get_dict()
        if not isinstance(payload, dict) or "resultSets" not in payload:
            raise SchemaError("nba_api response is not a resultSets payload")
        return RawResponse(payload=payload, body=body.encode("utf-8"), url=response.get_url(), params=params)

    return with_retries(once)


def fetch_players_raw(season: str) -> RawResponse:
    from nba_api.stats.endpoints import commonallplayers

    validate_season(season)
    params = {"is_only_current_season": 1, "season": season}
    return _call_endpoint(
        lambda: commonallplayers.CommonAllPlayers(is_only_current_season=1, season=season, timeout=NBA_TIMEOUT_S),
        params,
    )


def fetch_season_totals_raw(season: str, season_type: str = "Regular Season") -> RawResponse:
    from nba_api.stats.endpoints import leaguedashplayerstats

    validate_season(season)
    validate_season_type(season_type)
    params = {"season": season, "per_mode_detailed": "Totals", "season_type_all_star": season_type}
    return _call_endpoint(
        lambda: leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            per_mode_detailed="Totals",
            season_type_all_star=season_type,
            timeout=NBA_TIMEOUT_S,
        ),
        params,
    )


def fetch_game_logs_raw(season: str, season_type: str = "Regular Season") -> RawResponse:
    from nba_api.stats.endpoints import playergamelogs

    validate_season(season)
    validate_season_type(season_type)
    params = {"season_nullable": season, "season_type_nullable": season_type}
    return _call_endpoint(
        lambda: playergamelogs.PlayerGameLogs(
            season_nullable=season, season_type_nullable=season_type, timeout=NBA_TIMEOUT_S
        ),
        params,
    )


def fetch_active_players(season: str) -> pd.DataFrame:
    return normalize_players(fetch_players_raw(season).payload, season)


def fetch_season_totals(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    return normalize_season_totals(fetch_season_totals_raw(season, season_type).payload, season, season_type)


def fetch_game_logs(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    return normalize_game_logs(fetch_game_logs_raw(season, season_type).payload, season, season_type)
