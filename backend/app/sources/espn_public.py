"""ESPN fantasy public read endpoints (no cookies) via httpx.

``parse_players`` / ``parse_schedule`` are pure functions over parsed JSON; ``fetch_*_raw`` do the
HTTP with timeouts and bounded retries; ``fetch_*`` compose the two. See docs/DATA_SOURCES.md for
the verified field map.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import pandas as pd

from app.league.config import (
    ESPN_DEFAULT_POSITION_ID_TO_NAME,
    eligible_positions_from_espn_slots,
)
from app.sources.base import RawResponse, SchemaError, utc_now_iso, with_retries
from app.sources.teams import espn_team_id_to_tricode

log = logging.getLogger(__name__)

SOURCE = "espn_public"
ESPN_TIMEOUT_S = 60
ESPN_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season_id}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
ENDPOINT_PLAYERS = "players"
ENDPOINT_SCHEDULE = "schedule"
PLAYERS_LIMIT = 2000

# ESPN stat key -> normalized field (season totals; percentages are never stored).
ESPN_STAT_KEYS: dict[str, str] = {
    "42": "gp",
    "40": "min",
    "0": "pts",
    "6": "reb",
    "3": "ast",
    "2": "stl",
    "1": "blk",
    "17": "fg3m",
    "18": "fg3a",
    "13": "fgm",
    "14": "fga",
    "15": "ftm",
    "16": "fta",
    "11": "tov",
}
STAT_FIELDS: tuple[str, ...] = tuple(ESPN_STAT_KEYS.values())
PROJ_COLUMNS: tuple[str, ...] = tuple(f"proj_{f}" for f in STAT_FIELDS)
PREV_COLUMNS: tuple[str, ...] = tuple(f"prev_{f}" for f in STAT_FIELDS)
PLAYERS_COLUMNS: tuple[str, ...] = (
    "espn_id",
    "name",
    "team",
    "espn_team_id",
    "primary_position",
    "eligible_slots_json",
    "eligible_positions_json",
    "injury_status",
    "injured",
    "active",
    "adp",
    "percent_owned",
    "auction_value_avg",
    "adp_asof",
    "rank_standard",
    "rank_roto",
    *PROJ_COLUMNS,
    *PREV_COLUMNS,
    "source",
    "fetched_at",
    "season_id",
)
SCHEDULE_COLUMNS: tuple[str, ...] = (
    "game_id",
    "date_utc",
    "scoring_period_id",
    "home_team",
    "away_team",
    "season_id",
    "source",
    "fetched_at",
)
STAT_SOURCE_PROJECTION = "10"
STAT_SOURCE_ACTUAL = "00"


def players_url(season_id: int) -> str:
    return ESPN_BASE.format(season_id=season_id) + "/players"


def schedule_url(season_id: int) -> str:
    return ESPN_BASE.format(season_id=season_id)


def players_filter(season_id: int) -> dict[str, Any]:
    """The ``x-fantasy-filter`` header that selects projection, current and prior-season splits."""
    return {
        "players": {
            "filterActive": {"value": True},
            "limit": PLAYERS_LIMIT,
            "filterStatsForTopScoringPeriodIds": {
                "value": 2,
                "additionalValue": [
                    stat_split_id(season_id, "actual"),
                    stat_split_id(season_id, "projection"),
                    stat_split_id(season_id - 1, "actual"),
                ],
            },
            "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"},
        }
    }


def stat_split_id(season_id: int, kind: Literal["projection", "actual"]) -> str:
    """``10{season}`` = ESPN projection (statSourceId 1), ``00{season}`` = actual totals."""
    prefix = STAT_SOURCE_PROJECTION if kind == "projection" else STAT_SOURCE_ACTUAL
    return f"{prefix}{int(season_id)}"


# --- players ---------------------------------------------------------------------------------


def split_totals(stats: Any, split_id: str) -> dict[str, float | None] | None:
    """Season totals of one stat split, or None when the split is absent or has no numbers."""
    if not isinstance(stats, list):
        return None
    for entry in stats:
        if not isinstance(entry, dict) or str(entry.get("id")) != split_id:
            continue
        values = entry.get("stats")
        if not isinstance(values, dict) or not values:
            return None
        return {field: _float_or_none(values.get(key)) for key, field in ESPN_STAT_KEYS.items()}
    return None


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ms_to_iso(ms: Any) -> str | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0, UTC).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _rank(ranks: Any, rank_type: str) -> int | None:
    if not isinstance(ranks, dict):
        return None
    entry = ranks.get(rank_type)
    if not isinstance(entry, dict) or entry.get("rank") is None:
        return None
    return int(entry["rank"])


def parse_player(p: dict[str, Any], season_id: int) -> dict[str, Any]:
    """One ESPN player object -> flat record (pure)."""
    if not isinstance(p, dict) or "id" not in p or "fullName" not in p:
        raise SchemaError(f"ESPN player object lacks id/fullName: {str(p)[:120]}")
    slots = [int(s) for s in (p.get("eligibleSlots") or [])]
    positions = sorted(eligible_positions_from_espn_slots(slots))
    team_id = int(p.get("proTeamId") or 0)
    ownership = p.get("ownership") if isinstance(p.get("ownership"), dict) else {}
    proj = split_totals(p.get("stats"), stat_split_id(season_id, "projection")) or {}
    prev = split_totals(p.get("stats"), stat_split_id(season_id - 1, "actual")) or {}
    record: dict[str, Any] = {
        "espn_id": int(p["id"]),
        "name": str(p["fullName"]),
        "team": espn_team_id_to_tricode(team_id),
        "espn_team_id": team_id,
        "primary_position": ESPN_DEFAULT_POSITION_ID_TO_NAME.get(int(p.get("defaultPositionId") or 0)),
        "eligible_slots_json": json.dumps(slots),
        "eligible_positions_json": json.dumps(positions),
        "injury_status": p.get("injuryStatus"),
        "injured": bool(p.get("injured", False)),
        "active": bool(p.get("active", False)),
        "adp": _float_or_none(ownership.get("averageDraftPosition")),
        "percent_owned": _float_or_none(ownership.get("percentOwned")),
        "auction_value_avg": _float_or_none(ownership.get("auctionValueAverage")),
        "adp_asof": _ms_to_iso(ownership.get("date")),
        "rank_standard": _rank(p.get("draftRanksByRankType"), "STANDARD"),
        "rank_roto": _rank(p.get("draftRanksByRankType"), "ROTO"),
    }
    record.update({f"proj_{f}": proj.get(f) for f in STAT_FIELDS})
    record.update({f"prev_{f}": prev.get(f) for f in STAT_FIELDS})
    return record


_PLAYER_DTYPES: dict[str, str] = {
    "espn_id": "int64",
    "name": "str",
    "team": "str",
    "espn_team_id": "int64",
    "primary_position": "str",
    "eligible_slots_json": "str",
    "eligible_positions_json": "str",
    "injury_status": "str",
    "injured": "bool",
    "active": "bool",
    "adp": "float64",
    "percent_owned": "float64",
    "auction_value_avg": "float64",
    "adp_asof": "str",
    "rank_standard": "Int64",
    "rank_roto": "Int64",
    **{c: "float64" for c in PROJ_COLUMNS},
    **{c: "float64" for c in PREV_COLUMNS},
    "source": "str",
    "fetched_at": "str",
    "season_id": "int64",
}


def parse_players(json_list: Any, season_id: int, fetched_at: str | None = None) -> pd.DataFrame:
    """kona_player_info list -> espn_players table; only ``active`` players are kept."""
    if not isinstance(json_list, list):
        raise SchemaError("ESPN players payload must be a JSON list")
    records = [parse_player(p, season_id) for p in json_list if isinstance(p, dict) and p.get("active")]
    frame = pd.DataFrame.from_records(records, columns=list(PLAYERS_COLUMNS[:-3]))
    frame = frame.assign(source=SOURCE, fetched_at=fetched_at or utc_now_iso(), season_id=int(season_id))
    return frame.astype(_PLAYER_DTYPES)[list(PLAYERS_COLUMNS)]


# --- schedule --------------------------------------------------------------------------------


def parse_schedule(payload: Any, season_id: int, fetched_at: str | None = None) -> pd.DataFrame:
    """proTeamSchedules_wl -> one row per game (each game appears under both teams; de-duplicated)."""
    teams = payload.get("settings", {}).get("proTeams") if isinstance(payload, dict) else None
    if not isinstance(teams, list):
        raise SchemaError("ESPN schedule payload lacks settings.proTeams")
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for team in teams:
        games_by_period = team.get("proGamesByScoringPeriod") if isinstance(team, dict) else None
        for games in (games_by_period or {}).values():
            for g in games or []:
                if not isinstance(g, dict) or g.get("id") in seen:
                    continue
                seen.add(g["id"])
                rows.append(
                    {
                        "game_id": int(g["id"]),
                        "date_utc": _ms_to_iso(g.get("date")),
                        "scoring_period_id": int(g.get("scoringPeriodId") or 0),
                        "home_team": espn_team_id_to_tricode(g.get("homeProTeamId")),
                        "away_team": espn_team_id_to_tricode(g.get("awayProTeamId")),
                    }
                )
    frame = pd.DataFrame.from_records(rows, columns=list(SCHEDULE_COLUMNS[:5]))
    frame = frame.assign(season_id=int(season_id), source=SOURCE, fetched_at=fetched_at or utc_now_iso())
    frame = frame.astype(
        {"game_id": "int64", "date_utc": "str", "scoring_period_id": "int64", "home_team": "str", "away_team": "str"}
    )
    return frame.sort_values(["date_utc", "game_id"], kind="stable").reset_index(drop=True)


# --- fetching --------------------------------------------------------------------------------


def _get(url: str, params: dict[str, Any], headers: dict[str, str], client: httpx.Client | None) -> RawResponse:
    def once() -> RawResponse:
        own = client or httpx.Client(timeout=ESPN_TIMEOUT_S)
        try:
            r = own.get(url, params=params, headers=headers)
        finally:
            if client is None:
                own.close()
        r.raise_for_status()
        try:
            payload = r.json()
        except ValueError as exc:
            raise SchemaError(f"ESPN response is not JSON ({url})") from exc
        return RawResponse(payload=payload, body=r.content, url=str(r.url), params=params)

    return with_retries(once)


def fetch_players_raw(season_id: int, client: httpx.Client | None = None) -> RawResponse:
    headers = {
        "x-fantasy-filter": json.dumps(players_filter(season_id)),
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    raw = _get(players_url(season_id), {"view": "kona_player_info", "scoringPeriodId": 0}, headers, client)
    if not isinstance(raw.payload, list):
        raise SchemaError("ESPN players response is not a list")
    return raw


def fetch_schedule_raw(season_id: int, client: httpx.Client | None = None) -> RawResponse:
    raw = _get(
        schedule_url(season_id),
        {"view": "proTeamSchedules_wl"},
        {"User-Agent": USER_AGENT, "Accept": "application/json"},
        client,
    )
    if not isinstance(raw.payload, dict) or "settings" not in raw.payload:
        raise SchemaError("ESPN schedule response lacks settings")
    return raw


def fetch_players(season_id: int, client: httpx.Client | None = None) -> pd.DataFrame:
    return parse_players(fetch_players_raw(season_id, client).payload, season_id)


def fetch_schedule(season_id: int, client: httpx.Client | None = None) -> pd.DataFrame:
    return parse_schedule(fetch_schedule_raw(season_id, client).payload, season_id)
