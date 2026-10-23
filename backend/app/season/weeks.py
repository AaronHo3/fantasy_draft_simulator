"""Matchup-period calendar: which NBA dates belong to ESPN matchup period k.

ESPN basketball scoring periods are days; this league's matchup periods are Monday-anchored weeks
(period 1 starts on opening night, Tuesday 2026-10-20, and ends Sunday 2026-10-25). One period a
season is doubled around the All-Star break (``DOUBLE_PERIODS``), which is what makes the calendar
end on ESPN's ``finalScoringPeriod`` (160 -> 2027-03-28). ``calendar_matches_espn`` checks that.
Game dates are shifted by ``US_SHIFT_HOURS`` so a late US game stamped after UTC midnight stays on
its US date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from app.engine.schedule_model import US_SHIFT_HOURS

SEASON_STARTS: dict[str, date] = {"2026-27": date(2026, 10, 20)}
DOUBLE_PERIODS: dict[str, frozenset[int]] = {"2026-27": frozenset({18})}  # All-Star break: Feb 15-28, 2027
MAX_PERIOD = 22
WEEK_DAYS = 7


def season_start(season: str) -> date:
    try:
        return SEASON_STARTS[season]
    except KeyError as exc:
        raise ValueError(f"no opening date on file for season {season!r}") from exc


def _week_one_monday(season: str) -> date:
    start = season_start(season)
    return start - timedelta(days=start.weekday())


def _weeks_before(season: str, period: int) -> int:
    """Calendar weeks consumed by periods 1..period-1 (double periods take two)."""
    doubles = DOUBLE_PERIODS.get(season, frozenset())
    return sum(2 if p in doubles else 1 for p in range(1, period))


def period_window(season: str, period: int) -> tuple[date, date]:
    """Inclusive (first, last) date of matchup period ``period``; period 1 starts on opening night."""
    if period < 1:
        raise ValueError("period must be >= 1")
    monday = _week_one_monday(season) + timedelta(days=WEEK_DAYS * _weeks_before(season, period))
    first = season_start(season) if period == 1 else monday
    length = 2 if period in DOUBLE_PERIODS.get(season, frozenset()) else 1
    return first, monday + timedelta(days=WEEK_DAYS * length - 1)


def season_end(season: str) -> date:
    return period_window(season, MAX_PERIOD)[1]


def calendar_matches_espn(season: str, final_scoring_period: int) -> bool:
    """ESPN's finalScoringPeriod counts days from opening night; the calendar must end on that day."""
    return season_start(season) + timedelta(days=final_scoring_period - 1) == season_end(season)


def current_period(season: str, today: date) -> int:
    for p in range(1, MAX_PERIOD + 1):
        if today <= period_window(season, p)[1]:
            return p
    return MAX_PERIOD


def _us_date(stamp: str) -> date:
    return (datetime.fromisoformat(stamp) - timedelta(hours=US_SHIFT_HOURS)).date()


def games_in_window(schedule: pd.DataFrame, start: date, end: date) -> dict[str, int]:
    """Team tricode -> number of games whose US date falls in [start, end]."""
    if schedule.empty:
        return {}
    dates = schedule["date_utc"].map(_us_date)
    rows = schedule[(dates >= start) & (dates <= end)]
    counts: dict[str, int] = {}
    for col in ("home_team", "away_team"):
        for team, n in rows[col].value_counts().items():
            counts[str(team)] = counts.get(str(team), 0) + int(n)
    return counts


def first_scoring_period_id(season: str, period: int) -> int:
    """ESPN scoring periods are days numbered from opening night (1); the first day of a matchup period."""
    return (period_window(season, period)[0] - season_start(season)).days + 1
