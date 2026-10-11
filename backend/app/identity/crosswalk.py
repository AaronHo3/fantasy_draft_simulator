"""NBA <-> ESPN player id crosswalk.

Matching stages (``match_method``):

a. ``name_team``   normalized name and NBA tricode both equal, key unique on both sides (1.0)
b. ``name_unique`` normalized name unique across *all* records on both sides (0.9)
c. unresolved      ``nba_only`` / ``espn_only`` rows (confidence 0.0), also returned as a list

Two records sharing a normalized name are never merged unless their teams agree. The canonical
``player_id`` is ``nba:<nba_id>`` when an NBA id exists, else ``espn:<espn_id>``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.identity.players import normalize_name

CROSSWALK_COLUMNS: tuple[str, ...] = (
    "player_id",
    "nba_id",
    "espn_id",
    "name",
    "team",
    "match_method",
    "confidence",
)
CONFIDENCE: dict[str, float] = {"name_team": 1.0, "name_unique": 0.9, "nba_only": 0.0, "espn_only": 0.0}
NBA_REQUIRED = ("nba_id", "name", "team")
ESPN_REQUIRED = ("espn_id", "name", "team")


@dataclass(frozen=True)
class _Rec:
    id: int
    name: str
    team: str | None
    norm: str


def _records(frame: pd.DataFrame, id_col: str, required: tuple[str, ...]) -> list[_Rec]:
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"crosswalk input lacks columns {missing}")
    out: list[_Rec] = []
    for pid, name, team in zip(frame[id_col], frame["name"], frame["team"], strict=True):
        if pd.isna(pid) or pd.isna(name):
            continue
        team_s = None if pd.isna(team) or team == "" else str(team)
        out.append(_Rec(int(pid), str(name), team_s, normalize_name(str(name))))
    return out


def _unique_index(recs: list[_Rec], key) -> dict[Any, _Rec]:
    """key -> record for keys that occur exactly once (None keys skipped)."""
    groups: dict[Any, list[_Rec]] = defaultdict(list)
    for r in recs:
        k = key(r)
        if k is not None:
            groups[k].append(r)
    return {k: v[0] for k, v in groups.items() if len(v) == 1}


def _stage_name_team(nba: list[_Rec], espn: list[_Rec]) -> dict[int, int]:
    def key(r: _Rec) -> tuple[str, str] | None:
        return (r.norm, r.team) if r.team else None

    n_idx, e_idx = _unique_index(nba, key), _unique_index(espn, key)
    return {n_idx[k].id: e_idx[k].id for k in n_idx.keys() & e_idx.keys()}


def _stage_name_unique(
    nba: list[_Rec], espn: list[_Rec], matched_nba: set[int], matched_espn: set[int]
) -> dict[int, int]:
    n_counts, e_counts = Counter(r.norm for r in nba), Counter(r.norm for r in espn)
    n_by = {r.norm: r for r in nba if n_counts[r.norm] == 1 and r.id not in matched_nba}
    e_by = {r.norm: r for r in espn if e_counts[r.norm] == 1 and r.id not in matched_espn}
    return {n_by[k].id: e_by[k].id for k in n_by.keys() & e_by.keys()}


def _reason(r: _Rec, counts: Counter) -> str:
    if counts[r.norm] > 1:
        return "ambiguous_name" if r.team else "ambiguous_name_no_team"
    return "no_candidate"


def build_crosswalk(
    nba_players_df: pd.DataFrame,
    espn_players_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Link NBA and ESPN player records; inputs are read only, never mutated."""
    nba = _records(nba_players_df, "nba_id", NBA_REQUIRED)
    espn = _records(espn_players_df, "espn_id", ESPN_REQUIRED)
    espn_by_id = {r.id: r for r in espn}

    links: dict[int, tuple[int, str]] = {}
    for n_id, e_id in _stage_name_team(nba, espn).items():
        links[n_id] = (e_id, "name_team")
    used_espn = {e for e, _ in links.values()}
    for n_id, e_id in _stage_name_unique(nba, espn, set(links), used_espn).items():
        links[n_id] = (e_id, "name_unique")
    used_espn = {e for e, _ in links.values()}

    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    n_counts, e_counts = Counter(r.norm for r in nba), Counter(r.norm for r in espn)
    for r in nba:
        if r.id in links:
            e_id, method = links[r.id]
            e = espn_by_id[e_id]
            rows.append(_row(f"nba:{r.id}", r.id, e_id, r.name, r.team or e.team, method))
        else:
            rows.append(_row(f"nba:{r.id}", r.id, None, r.name, r.team, "nba_only"))
            unresolved.append(
                {"source": "nba_api", "id": r.id, "name": r.name, "team": r.team, "reason": _reason(r, n_counts)}
            )
    for r in espn:
        if r.id in used_espn:
            continue
        rows.append(_row(f"espn:{r.id}", None, r.id, r.name, r.team, "espn_only"))
        unresolved.append(
            {"source": "espn_public", "id": r.id, "name": r.name, "team": r.team, "reason": _reason(r, e_counts)}
        )
    frame = pd.DataFrame.from_records(rows, columns=list(CROSSWALK_COLUMNS)).astype(
        {
            "player_id": "str",
            "nba_id": "Int64",
            "espn_id": "Int64",
            "name": "str",
            "team": "str",
            "match_method": "str",
            "confidence": "float64",
        }
    )
    frame = frame.sort_values(["name", "player_id"], kind="stable").reset_index(drop=True)
    unresolved.sort(key=lambda d: (d["source"], d["name"]))
    return frame, unresolved


def _row(
    player_id: str, nba_id: int | None, espn_id: int | None, name: str, team: str | None, method: str
) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "nba_id": nba_id,
        "espn_id": espn_id,
        "name": name,
        "team": team,
        "match_method": method,
        "confidence": CONFIDENCE[method],
    }
