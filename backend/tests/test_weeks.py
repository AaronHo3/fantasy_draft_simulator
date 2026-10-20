from datetime import date

import pandas as pd

from app.season.weeks import current_period, games_in_window, period_window, season_start


def test_period_window_week1_and_2():
    assert season_start("2026-27") == date(2026, 10, 20)
    assert period_window("2026-27", 1) == (date(2026, 10, 20), date(2026, 10, 25))  # Oct 19 is a Monday
    assert period_window("2026-27", 2) == (date(2026, 10, 26), date(2026, 11, 1))
    assert period_window("2026-27", 19) == (date(2027, 3, 1), date(2027, 3, 7))  # after the doubled All-Star period


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


def test_all_star_period_spans_two_weeks_and_season_end_matches_espn():
    from app.season.weeks import calendar_matches_espn, season_end

    assert period_window("2026-27", 17) == (date(2027, 2, 8), date(2027, 2, 14))
    assert period_window("2026-27", 18) == (date(2027, 2, 15), date(2027, 2, 28))  # All-Star break week doubled
    assert period_window("2026-27", 19) == (date(2027, 3, 1), date(2027, 3, 7))
    assert period_window("2026-27", 22) == (date(2027, 3, 22), date(2027, 3, 28))
    assert season_end("2026-27") == date(2027, 3, 28)
    # ESPN reports finalScoringPeriod=160 (days from opening night): 2026-10-20 + 159 days = 2027-03-28
    assert calendar_matches_espn("2026-27", 160) is True
    assert calendar_matches_espn("2026-27", 167) is False
    assert current_period("2026-27", date(2027, 2, 26)) == 18
