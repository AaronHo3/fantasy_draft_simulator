"""Optional read-only import of a private ESPN league via the community ``espn_api`` client.

Requires the user's own SWID / espn_s2 cookies in backend/.env (COPILOT_ESPN_SWID, COPILOT_ESPN_S2).
Cookies never leave this process: they are passed to espn_api only and are not logged or returned.
Status: implemented against espn_api 1.0.1's documented objects, NOT verified against a real league
from this repository (no credentials available). Live draft syncing is not supported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.league.config import ESPN_SLOT_ID_TO_NAME, LeagueConfig, Manager, ScoringFormat

log = logging.getLogger(__name__)

# ESPN scoring type ids seen in league settings (mSettings.scoringSettings.scoringType)
SCORING_TYPE_MAP = {
    "H2H_CATEGORY": ScoringFormat.h2h_each_category,
    "H2H_MOST_CATEGORIES": ScoringFormat.h2h_most_categories,
    "ROTO": ScoringFormat.roto,
    "H2H_POINTS": None,
    "TOTAL_SEASON_POINTS": None,
}
# ESPN stat ids -> our category keys (espn_api basketball/constant STATS_MAP)
STAT_ID_TO_CATEGORY = {
    0: "PTS",
    6: "REB",
    3: "AST",
    2: "STL",
    1: "BLK",
    17: "FG3M",
    19: "FG_PCT",
    20: "FT_PCT",
    11: "TOV",
}


@dataclass(frozen=True)
class PrivateImportResult:
    league: LeagueConfig | None
    picks: list[dict[str, Any]]  # {overall, manager_id, espn_player_id, player_name, is_keeper}
    warnings: list[str]
    raw_scoring_type: str | None


def _slot_counts_to_lists(lineup_slot_counts: dict[str, int]) -> tuple[list[str], int, int]:
    starting: list[str] = []
    bench = ir = 0
    for sid, count in sorted(lineup_slot_counts.items(), key=lambda kv: int(kv[0])):
        name = ESPN_SLOT_ID_TO_NAME.get(int(sid))
        if not name or count <= 0:
            continue
        if name == "BENCH":
            bench = count
        elif name == "IR":
            ir = count
        else:
            starting.extend([name] * count)
    return starting, bench, ir


def league_config_from_settings(
    settings_json: dict[str, Any], teams_json: list[dict[str, Any]], user_team_id: int | None, season: str
) -> tuple[LeagueConfig | None, list[str], str | None]:
    """Pure conversion of ESPN ``mSettings`` + ``mTeam`` payloads into a LeagueConfig (or None with reasons)."""
    warnings: list[str] = []
    s = settings_json.get("settings", settings_json)
    scoring = s.get("scoringSettings", {})
    stype = scoring.get("scoringType")
    fmt = SCORING_TYPE_MAP.get(stype)
    if fmt is None:
        return None, [f"unsupported or unknown ESPN scoringType {stype!r}; configure the league manually"], stype
    cats = []
    for item in scoring.get("scoringItems", []):
        key = STAT_ID_TO_CATEGORY.get(int(item.get("statId", -1)))
        if key is None:
            warnings.append(f"ESPN stat id {item.get('statId')} is not a supported category; ignored")
        else:
            cats.append(key)
    from app.league.config import DEFAULT_NINE_CATEGORIES

    chosen = [c for c in DEFAULT_NINE_CATEGORIES if c.key in cats] or list(DEFAULT_NINE_CATEGORIES)
    if len(chosen) != len(cats):
        warnings.append("category list differed from the default nine; using the supported subset")
    roster = s.get("rosterSettings", {})
    starting, bench, ir = _slot_counts_to_lists(roster.get("lineupSlotCounts", {}))
    if not starting:
        return None, ["no lineup slots found in settings"], stype
    managers = []
    for t in teams_json:
        tid = int(t["id"])
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip() or f"Team {tid}"
        managers.append(Manager(id=f"espn-team-{tid}", name=name, is_user=(tid == user_team_id)))
    if not managers:
        return None, ["no teams in league payload"], stype
    user_id = f"espn-team-{user_team_id}" if user_team_id is not None else managers[0].id
    if user_team_id is None:
        warnings.append("user team not identified; defaulting to the first team, change it in setup")
    draft = s.get("draftSettings", {})
    order_ids = [f"espn-team-{int(t)}" for t in draft.get("pickOrder", [])] or [m.id for m in managers]
    if draft.get("type") == "AUCTION":
        return None, ["auction drafts are not supported"], stype
    acquisition = s.get("acquisitionSettings", {})
    lineup_mode = "daily" if roster.get("lineupLocktimeType", "INDIVIDUAL_GAME") == "INDIVIDUAL_GAME" else "weekly"
    caps = {}
    for pid, cap in roster.get("positionLimits", {}).items():
        name = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}.get(int(pid))
        if name and int(cap) > 0 and int(cap) < 99:
            caps[name] = int(cap)
    cfg = LeagueConfig(
        name=s.get("name", "ESPN league"),
        season=season,
        scoring_format=fmt,
        categories=chosen,
        managers=managers,
        user_manager_id=user_id,
        starting_slots=starting,
        bench_slots=bench,
        ir_slots=ir,
        draft_order=order_ids,
        position_caps=caps,
        lineup_mode=lineup_mode,
        max_games_per_week=acquisition.get("matchupAcquisitionLimit")
        if acquisition.get("isUsingAcquisitionBudget")
        else None,
        regular_season_weeks=int(s.get("scheduleSettings", {}).get("matchupPeriodCount", 19)),
        playoff_weeks=int(s.get("scheduleSettings", {}).get("playoffMatchupPeriodLength", 1)) or 1,
    )
    return cfg, warnings, stype


def picks_from_draft_detail(draft_json: dict[str, Any], players_by_id: dict[int, str]) -> list[dict[str, Any]]:
    """Pure conversion of ``mDraftDetail`` picks into ordered pick rows."""
    picks = draft_json.get("draftDetail", draft_json).get("picks", [])
    rows = []
    for p in sorted(picks, key=lambda x: int(x.get("overallPickNumber", 0))):
        rows.append(
            {
                "overall": int(p["overallPickNumber"]),
                "manager_id": f"espn-team-{int(p['teamId'])}",
                "espn_player_id": int(p["playerId"]),
                "player_name": players_by_id.get(int(p["playerId"]), ""),
                "is_keeper": bool(p.get("keeper", False)),
            }
        )
    return rows


def fetch_private_league(
    league_id: int, season_id: int, swid: str, espn_s2: str, user_team_id: int | None = None
) -> PrivateImportResult:
    """Network call through espn_api. Cookies are used only here and never logged."""
    from espn_api.basketball import League  # imported lazily: optional dependency path

    league = League(league_id=league_id, year=season_id, espn_s2=espn_s2, swid=swid)
    settings_json = league.espn_request.get_league()
    teams_json = settings_json.get("teams", [])
    season = f"{season_id - 1}-{str(season_id)[-2:]}"
    cfg, warnings, stype = league_config_from_settings(settings_json, teams_json, user_team_id, season)
    draft_json = league.espn_request.get_league_draft()
    names = {int(getattr(p, "playerId", 0)): getattr(p, "name", "") for t in league.teams for p in t.roster}
    picks = picks_from_draft_detail(draft_json, names)
    warnings.append("Imported read-only from ESPN; verify every setting in the setup screen before drafting.")
    return PrivateImportResult(cfg, picks, warnings, stype)
