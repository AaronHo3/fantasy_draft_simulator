"""Map session managers to ESPN teams by roster overlap (owner names are only a tie-breaker)."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.draft.events import DraftState
from app.identity.players import normalize_name
from app.projections.snapshot import Snapshot
from app.sources.espn_league import EspnLeague

HIGH_OVERLAP = 0.6
MEDIUM_OVERLAP = 0.3


@dataclass(frozen=True)
class TeamMatch:
    manager_id: str
    team_id: int
    overlap: float
    name_similarity: float
    confidence: str  # high | medium | low


@dataclass(frozen=True)
class TeamMapping:
    matches: tuple[TeamMatch, ...]
    unmatched_managers: tuple[str, ...]
    unmatched_teams: tuple[int, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, int]:
        return {m.manager_id: m.team_id for m in self.matches}


def _confidence(overlap: float) -> str:
    if overlap >= HIGH_OVERLAP:
        return "high"
    if overlap >= MEDIUM_OVERLAP:
        return "medium"
    return "low"


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def _overlap(session_ids: frozenset[str], espn_ids: frozenset[int], by_espn: dict[int, str]) -> float:
    if not session_ids:
        return 0.0
    canonical = {by_espn[e] for e in espn_ids if e in by_espn}
    return len(session_ids & canonical) / len(session_ids)


def match_teams(
    state: DraftState, league: EspnLeague, snap: Snapshot, overrides: dict[str, int] | None = None
) -> TeamMapping:
    """Greedy maximum-overlap assignment; ``overrides`` (manager -> team) are fixed first."""
    by_espn = {p.espn_id: p.player_id for p in snap.players if p.espn_id}
    managers = state.league.managers
    rosters = {m.id: frozenset(state.current_roster(m.id)) for m in managers}
    teams = {t.team_id: t for t in league.teams}
    scores = {
        (m.id, t.team_id): (_overlap(rosters[m.id], t.player_ids, by_espn), _name_similarity(m.name, t.owner_name))
        for m in managers
        for t in teams.values()
    }
    matches: list[TeamMatch] = []
    warnings: list[str] = []
    used_m: set[str] = set()
    used_t: set[int] = set()
    for mid, tid in (overrides or {}).items():
        if mid not in rosters or tid not in teams:
            warnings.append(f"override {mid}->{tid} ignored: unknown manager or team")
            continue
        ov, ns = scores[(mid, tid)]
        matches.append(TeamMatch(mid, tid, ov, ns, "override"))
        warnings.append(f"{mid} mapped to ESPN team {tid} by override (roster overlap {ov:.0%})")
        used_m.add(mid)
        used_t.add(tid)
    ranked = sorted(scores.items(), key=lambda kv: (kv[1][0], kv[1][1]), reverse=True)
    for (mid, tid), (ov, ns) in ranked:
        if mid in used_m or tid in used_t:
            continue
        matches.append(TeamMatch(mid, tid, ov, ns, _confidence(ov)))
        used_m.add(mid)
        used_t.add(tid)
        if ov < MEDIUM_OVERLAP:
            warnings.append(f"{mid} -> ESPN team {tid} is a weak match (overlap {ov:.0%}); check it")
    order = {m.id: i for i, m in enumerate(managers)}
    matches.sort(key=lambda m: order[m.manager_id])
    return TeamMapping(
        matches=tuple(matches),
        unmatched_managers=tuple(m.id for m in managers if m.id not in used_m),
        unmatched_teams=tuple(t for t in teams if t not in used_t),
        warnings=tuple(warnings),
    )
