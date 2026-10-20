from datetime import date

import pandas as pd

from app.season.weeks import current_period, games_in_window, period_window, season_start


def test_period_window_week1_and_2():
    assert season_start("2026-27") == date(2026, 10, 20)
    assert period_window("2026-27", 1) == (date(2026, 10, 20), date(2026, 10, 25))  # Oct 19 is a Monday
    assert period_window("2026-27", 2) == (date(2026, 10, 26), date(2026, 11, 1))
    assert period_window("2026-27", 19) == (date(2027, 2, 22), date(2027, 2, 28))


def test_games_in_window_counts_us_dates():
    frame = pd.DataFrame(
        {
            "game_id": [1, 2, 3, 4],
            "date_utc": [
                "2026-10-20T23:00:00+00:00",  # Oct 20 US evening
                "2026-10-26T01:30:00+00:00",  # Oct 25 US evening -> still period 1
                "2026-10-26T23:00:00+00:00",  # Oct 26 -> period 2
                "2026-10-19T23:00:00+00:00",  # before the season
            ],
            "home_team": ["DET", "LAL", "BOS", "NYK"],
            "away_team": ["BOS", "GSW", "DET", "PHI"],
        }
    )
    counts = games_in_window(frame, date(2026, 10, 20), date(2026, 10, 25))
    assert counts == {"DET": 1, "BOS": 1, "LAL": 1, "GSW": 1}


def test_current_period():
    assert current_period("2026-27", date(2026, 10, 19)) == 1
    assert current_period("2026-27", date(2026, 10, 25)) == 1
    assert current_period("2026-27", date(2026, 10, 26)) == 2
    assert current_period("2026-27", date(2027, 6, 1)) == 22
