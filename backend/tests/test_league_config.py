import pytest

from app.league.config import (
    DEFAULT_NINE_CATEGORIES,
    LeagueConfig,
    Manager,
    ScoringFormat,
    demo_league_config,
    eligible_positions_from_espn_slots,
    espn_season_id,
    nba_season_from_espn,
)


def test_espn_season_id_is_end_year():
    assert espn_season_id("2026-27") == 2027
    assert espn_season_id("2025-26") == 2026
    assert nba_season_from_espn(2027) == "2026-27"
    with pytest.raises(ValueError):
        espn_season_id("2026-28")


def test_default_nine_categories_direction_and_ratios():
    keys = [c.key for c in DEFAULT_NINE_CATEGORIES]
    assert keys == ["PTS", "REB", "AST", "STL", "BLK", "FG3M", "FG_PCT", "FT_PCT", "TOV"]
    tov = next(c for c in DEFAULT_NINE_CATEGORIES if c.key == "TOV")
    assert tov.higher_is_better is False
    fg = next(c for c in DEFAULT_NINE_CATEGORIES if c.key == "FG_PCT")
    assert (fg.numerator, fg.denominator) == ("FGM", "FGA")


def test_eligible_positions_from_espn_slots_ignores_composite_slots():
    # Russell Westbrook sample: [0, 5, 8, 11, 12, 13] -> PG, G, G/F, UTIL, BE, IR
    assert eligible_positions_from_espn_slots([0, 5, 8, 11, 12, 13]) == frozenset({"PG"})
    # Giannis sample: [3, 4, 6, 8, 9, 10, 11, 12, 13] -> PF and C
    assert eligible_positions_from_espn_slots([3, 4, 6, 8, 9, 10, 11, 12, 13]) == frozenset({"PF", "C"})


def test_demo_league_defaults():
    cfg = demo_league_config()
    assert cfg.n_managers == 12
    assert cfg.user_manager_id == "m06"
    assert cfg.roster_size == 13
    assert cfg.scoring_format == ScoringFormat.h2h_each_category
    assert cfg.tie_rule.each_category_tie_value == 0.5
    assert cfg.position_caps == {"C": 4} and cfg.ir_slots == 1
    assert cfg.format_confirmed is False
    assert cfg.draft_order[5] == "m06"


def test_validation_errors():
    ms = [Manager(id="a", name="A"), Manager(id="b", name="B")]
    with pytest.raises(ValueError):
        LeagueConfig(managers=ms, user_manager_id="zz")
    with pytest.raises(ValueError):
        LeagueConfig(managers=ms, user_manager_id="a", draft_order=["a", "a"])
    with pytest.raises(ValueError):
        LeagueConfig(managers=ms, user_manager_id="a", starting_slots=["PG", "BENCH"])
    with pytest.raises(ValueError):
        LeagueConfig(managers=ms, user_manager_id="a", position_caps={"GUARD": 3})


def test_league_config_espn_fields_validate():
    from app.league.config import LeagueConfig, demo_league_config

    cfg = demo_league_config(user_pick=1, n_managers=3)
    assert cfg.espn_league_id is None and cfg.espn_team_ids == {} and cfg.espn_linked_at is None
    linked = cfg.model_copy(update={"espn_league_id": 2075231076, "espn_team_ids": {"m01": 1, "m02": 7}})
    rt = LeagueConfig.model_validate_json(linked.model_dump_json())
    assert rt.espn_team_ids == {"m01": 1, "m02": 7}
    import pytest

    with pytest.raises(ValueError):
        LeagueConfig.model_validate({**cfg.model_dump(mode="json"), "espn_team_ids": {"m01": 1, "m02": 1}})
    with pytest.raises(ValueError):
        LeagueConfig.model_validate({**cfg.model_dump(mode="json"), "espn_team_ids": {"zz": 1}})
