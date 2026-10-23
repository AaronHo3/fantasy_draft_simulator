"""Public ESPN fantasy league read endpoint (no cookies) -> frozen league objects.

``parse_league`` is pure over parsed JSON; ``fetch_league_raw`` does the HTTP with bounded retries.
Verified against league 2075231076 on 2026-10-19 (see docs/DATA_SOURCES.md). Read-only: GET only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.league.config import LeagueConfig, LineupMode, ScoringFormat
from app.sources.base import FetchError, RawResponse, SchemaError, with_retries
from app.sources.espn_private import STAT_ID_TO_CATEGORY, _slot_counts_to_lists
from app.sources.espn_public import ESPN_BASE, ESPN_TIMEOUT_S, USER_AGENT

log = logging.getLogger(__name__)

# mMatchup carries the scored schedule (mSchedule would replace it with an unscored copy);
# mMatchupScore adds cumulativeScoreLive, the live scoreboard ESPN's site shows.
LEAGUE_VIEWS = ("mTeam", "mRoster", "mSettings", "mMatchup", "mMatchupScore", "mTransactions2", "mStatus")
ROSTER_MOVE_KINDS = frozenset({"ADD", "DROP", "TRADE"})
IR_SLOT_ID = 13
CENTER_POSITION_ID = 5
SCORING_TYPE_TO_FORMAT = {
    "H2H_CATEGORY": ScoringFormat.h2h_each_category,
    "H2H_MOST_CATEGORIES": ScoringFormat.h2h_most_categories,
    "ROTO": ScoringFormat.roto,
}


class LeagueAccessError(RuntimeError):
    """ESPN refused the league (private league without cookies)."""


@dataclass(frozen=True)
class EspnSettings:
    name: str
    scoring_type: str
    stat_ids: tuple[int, ...]
    lineup_slot_counts: dict[int, int]
    position_limits: dict[int, int]
    lineup_lock_type: str
    matchup_period_count: int
    playoff_team_count: int
    current_matchup_period: int
    scoring_period_id: int
    final_scoring_period: int = 0  # days from opening night; 0 when absent


@dataclass(frozen=True)
class EspnRosterEntry:
    espn_player_id: int
    name: str
    lineup_slot_id: int
    injury_status: str
    acquisition_type: str
    pro_team_id: int | None

    @property
    def on_ir(self) -> bool:
        return self.lineup_slot_id == IR_SLOT_ID


@dataclass(frozen=True)
class EspnTeam:
    team_id: int
    abbrev: str
    name: str
    owner_ids: tuple[str, ...]
    owner_name: str
    roster: tuple[EspnRosterEntry, ...]
    wins: int
    losses: int
    ties: int
    playoff_seed: int | None
    waiver_rank: int | None

    @property
    def player_ids(self) -> frozenset[int]:
        return frozenset(e.espn_player_id for e in self.roster)


@dataclass(frozen=True)
class EspnStatLine:
    score: float
    result: str | None


@dataclass(frozen=True)
class EspnMatchupSide:
    team_id: int
    by_stat: dict[int, EspnStatLine]
    record: tuple[int, int, int] = (0, 0, 0)  # category wins, losses, ties so far
    is_live: bool = False  # True when taken from cumulativeScoreLive (what ESPN's site shows)


@dataclass(frozen=True)
class EspnMatchup:
    matchup_id: int
    period: int
    home: EspnMatchupSide
    away: EspnMatchupSide | None
    winner: str


@dataclass(frozen=True)
class EspnTransactionItem:
    kind: str
    espn_player_id: int
    from_team_id: int
    to_team_id: int


@dataclass(frozen=True)
class EspnTransaction:
    transaction_id: str
    kind: str
    status: str
    team_id: int
    proposed_at: str
    scoring_period_id: int
    items: tuple[EspnTransactionItem, ...]

    @property
    def is_roster_move(self) -> bool:
        return self.status == "EXECUTED" and any(it.kind in ROSTER_MOVE_KINDS for it in self.items)


BOXSCORE_STAT_IDS = {
    0: "PTS",
    6: "REB",
    3: "AST",
    2: "STL",
    1: "BLK",
    11: "TOV",
    17: "FG3M",
    18: "FG3A",
    13: "FGM",
    14: "FGA",
    15: "FTM",
    16: "FTA",
}
BOXSCORE_GAMES_ID, BOXSCORE_MINUTES_ID = 42, 40


@dataclass(frozen=True)
class PlayerPeriodStats:
    """A player's stats as ESPN applied them to a fantasy team for one matchup period."""

    espn_player_id: int
    name: str
    lineup_slot_id: int
    games: int
    minutes: float
    stats: dict[str, float]  # keys of BOXSCORE_STAT_IDS


def parse_boxscore(payload: dict[str, Any], period: int) -> dict[int, list[PlayerPeriodStats]]:
    """mBoxscore view (requested with a scoringPeriodId inside ``period``) -> team id -> applied player stats.

    Matchup entries that have no ``rosterForMatchupPeriod`` yet (future periods) are skipped, so an
    empty dict means ESPN has nothing applied for that period.
    """
    out: dict[int, list[PlayerPeriodStats]] = {}
    for m in payload.get("schedule", []):
        if int(m.get("matchupPeriodId", -1)) != period:
            continue
        for side in ("home", "away"):
            s = m.get(side)
            if not isinstance(s, dict) or s.get("teamId") is None or "rosterForMatchupPeriod" not in s:
                continue
            rows = []
            for e in (s.get("rosterForMatchupPeriod") or {}).get("entries", []):
                pl = (e.get("playerPoolEntry") or {}).get("player") or {}
                blocks = pl.get("stats") or []
                raw = (blocks[0].get("stats") or {}) if blocks else {}

                def num(k: int) -> float:
                    try:
                        return float(raw.get(str(k), 0) or 0)
                    except (TypeError, ValueError):
                        return 0.0

                rows.append(
                    PlayerPeriodStats(
                        espn_player_id=int(e.get("playerId", pl.get("id", 0))),
                        name=str(pl.get("fullName", "")),
                        lineup_slot_id=int(e.get("lineupSlotId", -1)),
                        games=int(num(BOXSCORE_GAMES_ID)),
                        minutes=num(BOXSCORE_MINUTES_ID),
                        stats={key: num(sid) for sid, key in BOXSCORE_STAT_IDS.items()},
                    )
                )
            out[int(s["teamId"])] = rows
    return out


@dataclass(frozen=True)
class EspnLeague:
    league_id: int
    season_id: int
    settings: EspnSettings
    teams: tuple[EspnTeam, ...]
    matchups: tuple[EspnMatchup, ...]
    transactions: tuple[EspnTransaction, ...]
    fetched_at: str

    def team(self, team_id: int) -> EspnTeam:
        for t in self.teams:
            if t.team_id == team_id:
                return t
        raise KeyError(team_id)

    def matchups_for(self, period: int) -> tuple[EspnMatchup, ...]:
        return tuple(m for m in self.matchups if m.period == period)


# --- parsing ---------------------------------------------------------------------------------


def _epoch_ms_to_iso(ms: Any) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC).isoformat(timespec="seconds")


def _parse_settings(payload: dict[str, Any]) -> EspnSettings:
    s = payload.get("settings")
    if not isinstance(s, dict):
        raise SchemaError("ESPN league payload lacks settings")
    scoring, roster, sched = s.get("scoringSettings", {}), s.get("rosterSettings", {}), s.get("scheduleSettings", {})
    status = payload.get("status", {})
    return EspnSettings(
        name=str(s.get("name", "")).strip(),
        scoring_type=str(scoring.get("scoringType", "")),
        stat_ids=tuple(sorted(int(i["statId"]) for i in scoring.get("scoringItems", []))),
        lineup_slot_counts={int(k): int(v) for k, v in roster.get("lineupSlotCounts", {}).items()},
        position_limits={int(k): int(v) for k, v in roster.get("positionLimits", {}).items()},
        lineup_lock_type=str(roster.get("lineupLocktimeType", "")),
        matchup_period_count=int(sched.get("matchupPeriodCount", 0)),
        playoff_team_count=int(sched.get("playoffTeamCount", 0)),
        current_matchup_period=int(status.get("currentMatchupPeriod", 0)),
        scoring_period_id=int(payload.get("scoringPeriodId", 0)),
        final_scoring_period=int(status.get("finalScoringPeriod", 0) or 0),
    )


def _owner_names(payload: dict[str, Any]) -> dict[str, str]:
    out = {}
    for m in payload.get("members", []):
        name = f"{m.get('firstName', '')} {m.get('lastName', '')}".strip() or str(m.get("displayName", ""))
        out[str(m.get("id"))] = name
    return out


def _parse_entry(e: dict[str, Any]) -> EspnRosterEntry:
    p = e.get("playerPoolEntry", {}).get("player", {})
    return EspnRosterEntry(
        espn_player_id=int(e.get("playerId", p.get("id"))),
        name=str(p.get("fullName", "")),
        lineup_slot_id=int(e.get("lineupSlotId", -1)),
        injury_status=str(e.get("injuryStatus") or p.get("injuryStatus") or ""),
        acquisition_type=str(e.get("acquisitionType", "")),
        pro_team_id=int(p["proTeamId"]) if p.get("proTeamId") is not None else None,
    )


def _parse_team(t: dict[str, Any], owners: dict[str, str]) -> EspnTeam:
    rec = t.get("record", {}).get("overall", {})
    owner_ids = tuple(str(o) for o in t.get("owners", []))
    primary = str(t.get("primaryOwner") or (owner_ids[0] if owner_ids else ""))
    name = str(t.get("name") or "").strip()
    return EspnTeam(
        team_id=int(t["id"]),
        abbrev=str(t.get("abbrev", "")),
        name=name,
        owner_ids=owner_ids,
        owner_name=owners.get(primary) or name,
        roster=tuple(_parse_entry(e) for e in t.get("roster", {}).get("entries", [])),
        wins=int(rec.get("wins", 0)),
        losses=int(rec.get("losses", 0)),
        ties=int(rec.get("ties", 0)),
        playoff_seed=int(t["playoffSeed"]) if t.get("playoffSeed") is not None else None,
        waiver_rank=int(t["waiverRank"]) if t.get("waiverRank") is not None else None,
    )


def _parse_side(s: dict[str, Any] | None) -> EspnMatchupSide | None:
    if not s or s.get("teamId") is None:
        return None
    live = s.get("cumulativeScoreLive") or {}
    is_live = bool(live.get("scoreByStat"))
    cs = live if is_live else (s.get("cumulativeScore") or {})
    by_stat = {}
    for sid, line in (cs.get("scoreByStat") or {}).items():
        by_stat[int(sid)] = EspnStatLine(score=float(line.get("score") or 0.0), result=line.get("result"))
    record = (int(cs.get("wins") or 0), int(cs.get("losses") or 0), int(cs.get("ties") or 0))
    return EspnMatchupSide(team_id=int(s["teamId"]), by_stat=by_stat, record=record, is_live=is_live)


def _parse_matchup(m: dict[str, Any]) -> EspnMatchup:
    home = _parse_side(m.get("home"))
    if home is None:
        raise SchemaError(f"matchup {m.get('id')} has no home team")
    return EspnMatchup(
        matchup_id=int(m["id"]),
        period=int(m["matchupPeriodId"]),
        home=home,
        away=_parse_side(m.get("away")),
        winner=str(m.get("winner", "UNDECIDED")),
    )


def _parse_transaction(tx: dict[str, Any]) -> EspnTransaction:
    items = tuple(
        EspnTransactionItem(
            kind=str(it.get("type", "")),
            espn_player_id=int(it.get("playerId", 0)),
            from_team_id=int(it.get("fromTeamId", 0)),
            to_team_id=int(it.get("toTeamId", 0)),
        )
        for it in tx.get("items", [])
    )
    return EspnTransaction(
        transaction_id=str(tx.get("id", "")),
        kind=str(tx.get("type", "")),
        status=str(tx.get("status", "")),
        team_id=int(tx.get("teamId", 0)),
        proposed_at=_epoch_ms_to_iso(tx.get("proposedDate", 0)),
        scoring_period_id=int(tx.get("scoringPeriodId", 0)),
        items=items,
    )


def parse_league(payload: dict[str, Any], league_id: int, season_id: int, fetched_at: str) -> EspnLeague:
    if not isinstance(payload, dict) or "teams" not in payload:
        raise SchemaError("ESPN league payload lacks teams")
    owners = _owner_names(payload)
    return EspnLeague(
        league_id=league_id,
        season_id=season_id,
        settings=_parse_settings(payload),
        teams=tuple(_parse_team(t, owners) for t in payload["teams"]),
        matchups=tuple(_parse_matchup(m) for m in payload.get("schedule", [])),
        transactions=tuple(_parse_transaction(t) for t in payload.get("transactions", [])),
        fetched_at=fetched_at,
    )


# --- settings comparison -----------------------------------------------------------------------


def settings_diff(s: EspnSettings, league: LeagueConfig) -> list[str]:
    """Human-readable differences between ESPN settings and the session's LeagueConfig (never auto-applied)."""
    lines: list[str] = []
    fmt = SCORING_TYPE_TO_FORMAT.get(s.scoring_type)
    if fmt != league.scoring_format:
        lines.append(f"ESPN scoring type is {s.scoring_type}; the session uses {league.scoring_format.value}")
    espn_cats = {STAT_ID_TO_CATEGORY[i] for i in s.stat_ids if i in STAT_ID_TO_CATEGORY}
    ours = {c.key for c in league.categories}
    if espn_cats != ours:
        lines.append(f"ESPN categories {sorted(espn_cats)} differ from the session's {sorted(ours)}")
    starting, bench, ir = _slot_counts_to_lists({str(k): v for k, v in s.lineup_slot_counts.items()})
    if sorted(starting) != sorted(league.starting_slots):
        lines.append(f"ESPN starting slots {starting} differ from the session's {league.starting_slots}")
    if (bench, ir) != (league.bench_slots, league.ir_slots):
        lines.append(f"ESPN bench/IR {bench}/{ir} differ from the session's {league.bench_slots}/{league.ir_slots}")
    espn_c_cap = s.position_limits.get(CENTER_POSITION_ID, -1)
    espn_caps = {"C": espn_c_cap} if 0 < espn_c_cap < 99 else {}
    if espn_caps != {k: v for k, v in league.position_caps.items() if v > 0}:
        lines.append(f"ESPN position caps {espn_caps} differ from the session's {league.position_caps}")
    if s.lineup_lock_type == "INDIVIDUAL_GAME" and league.lineup_mode == LineupMode.weekly:
        lines.append("ESPN locks lineups per game (daily); the session is set to weekly")
    return lines


# --- fetching ----------------------------------------------------------------------------------


def league_url(league_id: int, season_id: int) -> str:
    return f"{ESPN_BASE.format(season_id=season_id)}/segments/0/leagues/{league_id}"


def _get_league(url: str, params: dict[str, Any], client: httpx.Client | None) -> RawResponse:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    def once() -> RawResponse:
        own = client or httpx.Client(timeout=ESPN_TIMEOUT_S)
        try:
            r = own.get(url, params=params, headers=headers)
        finally:
            if client is None:
                own.close()
        if r.status_code in (401, 403):
            raise LeagueAccessError(f"ESPN league is private or not viewable (HTTP {r.status_code})")
        r.raise_for_status()
        try:
            payload = r.json()
        except ValueError as exc:
            raise SchemaError(f"ESPN response is not JSON ({url})") from exc
        return RawResponse(payload=payload, body=r.content, url=str(r.url), params=params)

    return with_retries(once, retry_on=(httpx.HTTPError,))


def _merge_next_period_rosters(
    payload: dict[str, Any], league_id: int, season_id: int, client: httpx.Client | None
) -> None:
    """Replace each team's roster with the view for the next scoring period.

    ESPN's default ``mRoster`` view is the roster as it stood when the current scoring period (day)
    opened, so an add/drop made today only shows up under ``scoringPeriodId = current + 1``.
    Verified 2026-10-20 (an executed FREEAGENT transaction was missing from the default view).
    Best effort: on any failure the default rosters are kept.
    """
    current = payload.get("scoringPeriodId") or (payload.get("status") or {}).get("latestScoringPeriod")
    if not current:
        return
    try:
        nxt = _get_league(
            league_url(league_id, season_id), {"view": ["mRoster"], "scoringPeriodId": int(current) + 1}, client
        )
    except (httpx.HTTPError, FetchError, SchemaError, LeagueAccessError) as exc:
        log.warning("next-period roster view unavailable, using the default view: %s", exc)
        return
    rosters = {
        int(t["id"]): t.get("roster") for t in (nxt.payload or {}).get("teams", []) if isinstance(t, dict) and "id" in t
    }
    for t in payload.get("teams", []):
        r = rosters.get(int(t.get("id", -1)))
        if isinstance(r, dict) and isinstance(r.get("entries"), list):
            t["roster"] = r


def fetch_league_raw(league_id: int, season_id: int, client: httpx.Client | None = None) -> RawResponse:
    raw = _get_league(league_url(league_id, season_id), {"view": list(LEAGUE_VIEWS)}, client)
    if not isinstance(raw.payload, dict) or "teams" not in raw.payload:
        raise SchemaError("ESPN league response lacks teams")
    _merge_next_period_rosters(raw.payload, league_id, season_id, client)
    return raw


def fetch_boxscore_raw(
    league_id: int, season_id: int, scoring_period_id: int, client: httpx.Client | None = None
) -> dict[str, Any]:
    """mBoxscore for the matchup period containing ``scoring_period_id`` (applied per-player stats)."""
    raw = _get_league(
        league_url(league_id, season_id), {"view": ["mBoxscore"], "scoringPeriodId": scoring_period_id}, client
    )
    if not isinstance(raw.payload, dict) or "schedule" not in raw.payload:
        raise SchemaError("ESPN boxscore response lacks schedule")
    return raw.payload


def fetch_league(league_id: int, season_id: int, client: httpx.Client | None = None) -> EspnLeague:
    raw = fetch_league_raw(league_id, season_id, client)
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    return parse_league(raw.payload, league_id, season_id, fetched_at)
