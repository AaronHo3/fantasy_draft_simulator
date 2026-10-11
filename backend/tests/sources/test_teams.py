from __future__ import annotations

import pytest
from espn_api.basketball.constant import PRO_TEAM_MAP
from nba_api.stats.static import teams as nba_teams

from app.sources.teams import (
    ESPN_PRO_TEAM_MAP,
    NBA_TRICODES,
    espn_team_id_to_tricode,
    normalize_tricode,
)


def test_pro_team_map_matches_installed_espn_api():
    assert ESPN_PRO_TEAM_MAP == PRO_TEAM_MAP


def test_nba_tricodes_match_installed_nba_api_static_teams():
    assert NBA_TRICODES == {t["abbreviation"] for t in nba_teams.get_teams()}
    assert len(NBA_TRICODES) == 30


def test_every_espn_team_maps_to_exactly_one_nba_tricode():
    mapped = {normalize_tricode(v) for k, v in ESPN_PRO_TEAM_MAP.items() if k != 0}
    assert mapped == NBA_TRICODES


@pytest.mark.parametrize(
    ("abbrev", "expected"),
    [
        ("PHL", "PHI"),
        ("PHO", "PHX"),
        ("NO", "NOP"),
        ("GS", "GSW"),
        ("NY", "NYK"),
        ("SA", "SAS"),
        ("UTAH", "UTA"),
        ("WSH", "WAS"),
        ("BOS", "BOS"),
        ("bos", "BOS"),
        (" phi ", "PHI"),
        ("FA", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_tricode(abbrev, expected):
    assert normalize_tricode(abbrev) == expected


def test_normalize_tricode_rejects_unknown():
    with pytest.raises(ValueError, match="unknown team abbreviation"):
        normalize_tricode("SEA")


def test_espn_team_id_to_tricode():
    assert espn_team_id_to_tricode(0) is None and espn_team_id_to_tricode(None) is None
    assert espn_team_id_to_tricode(20) == "PHI" and espn_team_id_to_tricode(21) == "PHX"
    assert espn_team_id_to_tricode("2") == "BOS"
    with pytest.raises(ValueError):
        espn_team_id_to_tricode(99)
    with pytest.raises(ValueError):
        espn_team_id_to_tricode("abc")
