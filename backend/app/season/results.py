"""Actual weekly category results straight from ESPN's matchup scoreByStat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.engine.categories import ratio
from app.league.config import CategoryDef, CategoryKind
from app.sources.espn_league import EspnMatchup, EspnMatchupSide

ESPN_STAT_TO_KEY = {0: "PTS", 6: "REB", 3: "AST", 2: "STL", 1: "BLK", 17: "FG3M", 19: "FG_PCT", 20: "FT_PCT", 11: "TOV"}
KEY_TO_ESPN_STAT = {v: k for k, v in ESPN_STAT_TO_KEY.items()}
RATIO_PARTS = {"FG_PCT": (13, 14), "FT_PCT": (15, 16)}  # makes, attempts stat ids
TIE_CREDIT = 0.5


class HasMatchups(Protocol):
    def matchups_for(self, period: int) -> tuple[EspnMatchup, ...]: ...


@dataclass(frozen=True)
class WeekSide:
    manager_id: str
    values: dict[str, float | None]
    results: dict[str, str | None]
    cats_won: float


@dataclass(frozen=True)
class WeekMatchupResult:
    period: int
    home: WeekSide
    away: WeekSide | None
    winner: str


def _value(side: EspnMatchupSide, cat: CategoryDef) -> float | None:
    if cat.kind == CategoryKind.ratio and cat.key in RATIO_PARTS:
        makes_id, att_id = RATIO_PARTS[cat.key]
        if makes_id in side.by_stat and att_id in side.by_stat:
            return ratio(side.by_stat[makes_id].score, side.by_stat[att_id].score)
    line = side.by_stat.get(KEY_TO_ESPN_STAT.get(cat.key, -1))
    if line is None:
        return None
    if cat.kind == CategoryKind.ratio:
        return line.score if line.score > 0 else None
    return line.score


def _side(side: EspnMatchupSide, manager_id: str, categories: list[CategoryDef]) -> WeekSide:
    values = {c.key: _value(side, c) for c in categories}
    results = {
        c.key: (side.by_stat.get(KEY_TO_ESPN_STAT.get(c.key, -1)) or EspnStatLineNone).result for c in categories
    }
    won = sum(1.0 if r == "WIN" else TIE_CREDIT if r == "TIE" else 0.0 for r in results.values())
    return WeekSide(manager_id, values, results, won)


class _NoLine:
    result = None


EspnStatLineNone = _NoLine()


def week_results(
    league: HasMatchups, period: int, team_to_manager: dict[int, str], categories: list[CategoryDef]
) -> tuple[WeekMatchupResult, ...]:
    out = []
    for m in league.matchups_for(period):
        home_mid = team_to_manager.get(m.home.team_id, f"espn-team-{m.home.team_id}")
        home = _side(m.home, home_mid, categories)
        away = None
        if m.away is not None:
            away = _side(m.away, team_to_manager.get(m.away.team_id, f"espn-team-{m.away.team_id}"), categories)
        else:
            home = WeekSide(home.manager_id, home.values, dict.fromkeys(home.results), 0.0)
        out.append(WeekMatchupResult(period, home, away, m.winner))
    return tuple(out)
