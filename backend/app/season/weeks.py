"""Matchup-period calendar: which NBA dates belong to ESPN matchup period k.

ESPN basketball scoring periods are days; this league's matchup periods are Monday-anchored weeks
(period 1 starts on opening night, Tuesday 2026-10-20, and ends Sunday 2026-10-26). Game dates are
shifted by ``US_SHIFT_HOURS`` so a late US game stamped after UTC midnight stays on its US date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from app.engine.schedule_model import US_SHIFT_HOURS

SEASON_STARTS: dict[str, date] = {"2026-27": date(2026, 10, 20)}
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


def period_window(season: str, period: int) -> tuple[date, date]:
    """Inclusive (first, last) date of matchup period ``period``; period 1 starts on opening night."""
    if period < 1:
        raise ValueError("period must be >= 1")
    monday = _week_one_monday(season) + timedelta(days=WEEK_DAYS * (period - 1))
    first = season_start(season) if period == 1 else monday
    return first, monday + timedelta(days=WEEK_DAYS - 1)


def current_period(season: str, today: date) -> int:
    days = (today - _week_one_monday(season)).days
    return max(1, min(MAX_PERIOD, days // WEEK_DAYS + 1))


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
