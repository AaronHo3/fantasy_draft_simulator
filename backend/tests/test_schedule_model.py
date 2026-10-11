import numpy as np
import pandas as pd

from app.engine.schedule_model import (
    average_daily_counted_fraction,
    build_team_schedule,
    daily_counted_fraction,
    games_per_week_for_players,
)


def sched(rows):
    return pd.DataFrame(rows, columns=["game_id", "date_utc", "scoring_period_id", "home_team", "away_team"])


def test_build_team_schedule_weeks_and_counts():
    # Tue 2026-10-20 .. ; times are 00:00Z the next day for evening US games -> shift back 6h
    rows = [
        (1, "2026-10-21T00:00:00+00:00", 1, "BOS", "DET"),
        (2, "2026-10-22T02:00:00+00:00", 2, "BOS", "NYK"),
        (3, "2026-10-24T00:00:00+00:00", 4, "LAL", "BOS"),
        (4, "2026-10-27T00:00:00+00:00", 7, "BOS", "MIA"),
        (5, "2026-10-28T00:00:00+00:00", 8, "DET", "LAL"),
    ]
    ts = build_team_schedule(sched(rows))
    assert ts.weeks[0] == "2026-10-19" and len(ts.weeks) == 2
    assert ts.games("BOS", 0) == 3 and ts.games("BOS", 1) == 1 and ts.games("DET", 1) == 1
    assert ts.week_days["BOS"][0] == (1, 2, 4)  # Tue, Wed, Fri
    avg = ts.average_games_per_week()
    assert avg["BOS"] == 2.0  # no full weeks -> plain mean over all weeks


def test_daily_counted_fraction_caps_collisions():
    rows = []
    gid = 0
    # 4 teams all playing Mon..Thu of week 2026-10-19 (dates evening US -> +1 day UTC)
    for day in ("2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"):
        for home, away in (("AAA", "BBB"), ("CCC", "DDD")):
            gid += 1
            rows.append((gid, f"{day}T01:00:00+00:00", gid, home, away))
    ts = build_team_schedule(sched(rows))
    roster = ["AAA", "BBB", "CCC", "DDD"]
    f = daily_counted_fraction(roster, n_starting=2, ts=ts, week_idx=0)
    assert np.allclose(f, 0.5)  # 4 players, 2 slots every day
    f2 = daily_counted_fraction(roster, n_starting=4, ts=ts, week_idx=0)
    assert np.allclose(f2, 1.0)
    f3 = daily_counted_fraction(["AAA", None, "ZZZ"], n_starting=1, ts=ts, week_idx=0)
    assert f3[0] == 1.0 and f3[1] == 1.0  # unknown teams count fully (nothing to collide with)
    assert average_daily_counted_fraction(roster, 2, ts).shape == (4,)


def test_games_per_week_default():
    g = games_per_week_for_players(["BOS", None, "XXX"], {"BOS": 3.6})
    assert list(g) == [3.6, 3.5, 3.5]
