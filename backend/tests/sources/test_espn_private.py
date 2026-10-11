from app.league.config import ScoringFormat
from app.sources.espn_private import league_config_from_settings, picks_from_draft_detail

SETTINGS = {
    "settings": {
        "name": "Test 9cat",
        "scoringSettings": {
            "scoringType": "H2H_MOST_CATEGORIES",
            "scoringItems": [{"statId": i} for i in (0, 6, 3, 2, 1, 17, 19, 20, 11)],
        },
        "rosterSettings": {
            "lineupSlotCounts": {"0": 1, "1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "11": 3, "12": 3, "13": 1},
            "lineupLocktimeType": "INDIVIDUAL_GAME",
            "positionLimits": {"5": 4},
        },
        "draftSettings": {"type": "SNAKE", "pickOrder": [3, 1, 2]},
        "scheduleSettings": {"matchupPeriodCount": 19, "playoffMatchupPeriodLength": 2},
    }
}
TEAMS = [{"id": 1, "name": "Alpha"}, {"id": 2, "location": "Beta", "nickname": "Bears"}, {"id": 3, "name": "Gamma"}]


def test_settings_convert_to_league_config():
    cfg, warnings, stype = league_config_from_settings(SETTINGS, TEAMS, 2, "2026-27")
    assert stype == "H2H_MOST_CATEGORIES" and cfg is not None
    assert cfg.scoring_format == ScoringFormat.h2h_most_categories
    assert cfg.starting_slots == ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL", "UTIL", "UTIL"]
    assert cfg.bench_slots == 3 and cfg.ir_slots == 1 and cfg.position_caps == {"C": 4}
    assert cfg.draft_order == ["espn-team-3", "espn-team-1", "espn-team-2"]
    assert cfg.user_manager_id == "espn-team-2" and cfg.manager("espn-team-2").name == "Beta Bears"
    assert cfg.lineup_mode.value == "daily" and cfg.format_confirmed is False


def test_points_league_and_auction_rejected():
    s = {"settings": {**SETTINGS["settings"], "scoringSettings": {"scoringType": "H2H_POINTS", "scoringItems": []}}}
    cfg, warnings, _ = league_config_from_settings(s, TEAMS, 1, "2026-27")
    assert cfg is None and "unsupported" in warnings[0]
    s2 = {"settings": {**SETTINGS["settings"], "draftSettings": {"type": "AUCTION"}}}
    cfg2, w2, _ = league_config_from_settings(s2, TEAMS, 1, "2026-27")
    assert cfg2 is None and "auction" in w2[0]


def test_draft_detail_to_picks():
    d = {
        "draftDetail": {
            "picks": [
                {"overallPickNumber": 2, "teamId": 1, "playerId": 10, "keeper": False},
                {"overallPickNumber": 1, "teamId": 3, "playerId": 11, "keeper": True},
            ]
        }
    }
    rows = picks_from_draft_detail(d, {10: "A", 11: "B"})
    assert [r["overall"] for r in rows] == [1, 2] and rows[0]["is_keeper"] and rows[1]["player_name"] == "A"
