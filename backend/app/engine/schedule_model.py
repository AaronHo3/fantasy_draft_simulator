"""Schedule-aware games per week and daily-lineup collision factors.

Weeks are Monday-anchored US dates derived from the ESPN schedule (UTC timestamps shifted by 6 h);
ESPN matchup periods usually follow this pattern but the league's actual period boundaries are not
known here, so results are labeled approximate. Without a schedule, a generic 3.5 games/week applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

GENERIC_GAMES_PER_WEEK = 3.5
US_SHIFT_HOURS = 6


@dataclass(frozen=True)
class TeamSchedule:
    weeks: tuple[str, ...]  # ISO dates of the Monday starting each week
    week_days: dict[str, tuple[tuple[int, ...], ...]]  # team -> per week -> weekday indices (0=Mon) with a game

    def games(self, team: str, week_idx: int) -> int:
        return len(self.week_days.get(team, ())[week_idx]) if team in self.week_days else 0

    def full_week_indices(self) -> list[int]:
        """Weeks in which the median team plays at least 3 games (drops opening/closing partial weeks)."""
        out = []
        for w in range(len(self.weeks)):
            counts = [len(days[w]) for days in self.week_days.values()]
            if counts and float(np.median(counts)) >= 3:
                out.append(w)
        return out

    def average_games_per_week(self) -> dict[str, float]:
        idx = self.full_week_indices() or list(range(len(self.weeks)))
        return {t: float(np.mean([len(days[w]) for w in idx])) for t, days in self.week_days.items()}


def build_team_schedule(schedule: pd.DataFrame) -> TeamSchedule:
    """From normalized schedule rows (date_utc, home_team, away_team) to per-team weekly game days."""
    if schedule.empty:
        return TeamSchedule((), {})
    dates = [
        (datetime.fromisoformat(str(d).replace("Z", "+00:00")) - timedelta(hours=US_SHIFT_HOURS)).date()
        for d in schedule["date_utc"]
    ]
    mondays = [d - timedelta(days=d.weekday()) for d in dates]
    first, last = min(mondays), max(mondays)
    weeks = []
    m = first
    while m <= last:
        weeks.append(m)
        m += timedelta(days=7)
    week_idx = {w: i for i, w in enumerate(weeks)}
    tmp: dict[str, list[set[int]]] = {}
    for d, mon, home, away in zip(dates, mondays, schedule["home_team"], schedule["away_team"], strict=True):
        for team in (str(home), str(away)):
            if team not in tmp:
                tmp[team] = [set() for _ in weeks]
            tmp[team][week_idx[mon]].add(d.weekday())
    return TeamSchedule(
        tuple(w.isoformat() for w in weeks), {t: tuple(tuple(sorted(s)) for s in lst) for t, lst in tmp.items()}
    )


def games_per_week_for_players(teams: list[str | None], avg_games: dict[str, float]) -> np.ndarray:
    """Per-player expected games per week from their team's average; generic default when unknown."""
    return np.array([avg_games.get(t, GENERIC_GAMES_PER_WEEK) if t else GENERIC_GAMES_PER_WEEK for t in teams])


def daily_counted_fraction(
    roster_teams: list[str | None], n_starting: int, ts: TeamSchedule, week_idx: int
) -> np.ndarray:
    """Expected share of each roster player's games that fit into ``n_starting`` daily slots.

    On a day when k rostered players have games and k > n_starting, each is counted with probability
    n_starting / k (positions and lineup choices ignored: an approximation, labeled as such).
    """
    n = len(roster_teams)
    if n == 0:
        return np.zeros(0)
    plays = np.zeros((n, 7), dtype=bool)
    for i, t in enumerate(roster_teams):
        if t and t in ts.week_days and week_idx < len(ts.weeks):
            for wd in ts.week_days[t][week_idx]:
                plays[i, wd] = True
    k = plays.sum(axis=0)  # players with a game each day
    share = np.where(k > n_starting, n_starting / np.maximum(k, 1), 1.0)
    counted = (plays * share[None, :]).sum(axis=1)
    games = plays.sum(axis=1)
    return np.where(games > 0, counted / np.maximum(games, 1), 1.0)


def daily_counted_by_value(
    roster_teams: list[str | None], values: list[float], n_starting: int, ts: TeamSchedule, week_idx: int
) -> np.ndarray:
    """Share of each player's game days on which an active manager starts him.

    On a day when k rostered players have games and k > n_starting, the ``n_starting`` highest
    ``values`` play and the rest sit (positions ignored: an approximation, labeled as such). A
    player with no game that week counts 1.0 so the caller's games array decides.
    """
    n = len(roster_teams)
    if n == 0:
        return np.zeros(0)
    plays = np.zeros((n, 7), dtype=bool)
    for i, t in enumerate(roster_teams):
        if t and t in ts.week_days and week_idx < len(ts.weeks):
            for wd in ts.week_days[t][week_idx]:
                plays[i, wd] = True
    counted = np.zeros(n)
    order = np.argsort(-np.asarray(values, dtype=float), kind="stable")
    for day in range(7):
        slots = n_starting
        for i in order:
            if plays[i, day] and slots > 0:
                counted[i] += 1
                slots -= 1
    games = plays.sum(axis=1)
    return np.where(games > 0, counted / np.maximum(games, 1), 1.0)


def average_daily_counted_by_value(
    roster_teams: list[str | None], values: list[float], n_starting: int, ts: TeamSchedule
) -> np.ndarray:
    idx = ts.full_week_indices()
    if not idx:
        return np.ones(len(roster_teams))
    return np.mean([daily_counted_by_value(roster_teams, values, n_starting, ts, w) for w in idx], axis=0)


def average_daily_counted_fraction(roster_teams: list[str | None], n_starting: int, ts: TeamSchedule) -> np.ndarray:
    idx = ts.full_week_indices()
    if not idx:
        return np.ones(len(roster_teams))
    return np.mean([daily_counted_fraction(roster_teams, n_starting, ts, w) for w in idx], axis=0)
