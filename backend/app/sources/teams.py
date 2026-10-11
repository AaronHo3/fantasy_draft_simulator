"""NBA team identifiers across sources.

The engine uses NBA tricodes (``TEAM_ABBREVIATION`` from stats.nba.com) as the canonical team
key. ESPN uses its own integer ``proTeamId`` and two abbreviation flavours that differ from the
NBA tricodes: the community ``espn_api`` map (PHL, PHO) and ESPN's own web abbreviations
(PHI, PHX, NO, GS, NY, SA, UTAH, WSH). Everything here folds those into NBA tricodes.
"""

from __future__ import annotations

# Copy of espn_api.basketball.constant.PRO_TEAM_MAP (espn_api 1.0.1). tests/sources asserts equality
# with the installed package so drift is caught.
ESPN_PRO_TEAM_MAP: dict[int, str] = {
    0: "FA",
    1: "ATL",
    2: "BOS",
    3: "NOP",
    4: "CHI",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GSW",
    10: "HOU",
    11: "IND",
    12: "LAC",
    13: "LAL",
    14: "MIA",
    15: "MIL",
    16: "MIN",
    17: "BKN",
    18: "NYK",
    19: "ORL",
    20: "PHL",
    21: "PHO",
    22: "POR",
    23: "SAC",
    24: "SAS",
    25: "OKC",
    26: "UTA",
    27: "WAS",
    28: "TOR",
    29: "MEM",
    30: "CHA",
}

# The 30 NBA tricodes as used by stats.nba.com (nba_api.stats.static.teams).
NBA_TRICODES: frozenset[str] = frozenset(
    {
        "ATL",
        "BKN",
        "BOS",
        "CHA",
        "CHI",
        "CLE",
        "DAL",
        "DEN",
        "DET",
        "GSW",
        "HOU",
        "IND",
        "LAC",
        "LAL",
        "MEM",
        "MIA",
        "MIL",
        "MIN",
        "NOP",
        "NYK",
        "OKC",
        "ORL",
        "PHI",
        "PHX",
        "POR",
        "SAC",
        "SAS",
        "TOR",
        "UTA",
        "WAS",
    }
)

# Abbreviations seen in ESPN payloads / espn_api that are not NBA tricodes.
ESPN_ABBREV_TO_NBA_TRICODE: dict[str, str] = {
    "PHL": "PHI",
    "PHO": "PHX",
    "NO": "NOP",
    "GS": "GSW",
    "NY": "NYK",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
    "NOR": "NOP",
    "NJN": "BKN",
    "BRK": "BKN",
}

FREE_AGENT_MARKERS: frozenset[str] = frozenset({"", "FA", "NONE", "NULL"})


def normalize_tricode(abbrev: str | None) -> str | None:
    """Fold any ESPN/espn_api/NBA abbreviation to an NBA tricode; None for free agents/no team.

    Raises ``ValueError`` for an abbreviation that is not a known team, because silently keeping
    an unknown code would break team-based identity matching.
    """
    if abbrev is None:
        return None
    code = str(abbrev).strip().upper()
    if code in FREE_AGENT_MARKERS:
        return None
    code = ESPN_ABBREV_TO_NBA_TRICODE.get(code, code)
    if code not in NBA_TRICODES:
        raise ValueError(f"unknown team abbreviation {abbrev!r}")
    return code


def espn_team_id_to_tricode(team_id: int | None) -> str | None:
    """ESPN ``proTeamId`` -> NBA tricode; None for 0 (free agent) or missing."""
    if team_id is None:
        return None
    try:
        tid = int(team_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bad ESPN proTeamId {team_id!r}") from exc
    if tid not in ESPN_PRO_TEAM_MAP:
        raise ValueError(f"unknown ESPN proTeamId {tid}")
    return normalize_tricode(ESPN_PRO_TEAM_MAP[tid])
