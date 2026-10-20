"""Pure sync planner: ESPN rosters vs the event-replayed session rosters -> events to append.

A sync with no roster difference produces no events. One ``roster_changed`` event carries every
manager's moves (drops before adds) so a trade is atomic. Unknown ESPN players (not in the
snapshot) are kept as owned placeholders ``espn:<id>`` so they never appear as free agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.draft.events import DraftState, EventType
from app.projections.snapshot import Snapshot
from app.sources.espn_league import EspnLeague, EspnTeam

ROSTER_DIFF_REF = "espn:roster-diff"


@dataclass(frozen=True)
class RosterDiff:
    manager_id: str
    team_id: int
    added: tuple[str, ...]
    dropped: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class SyncPlan:
    fetched_at: str
    diffs: tuple[RosterDiff, ...]
    events: tuple[tuple[EventType, dict[str, Any], str], ...]
    warnings: tuple[str, ...]
    unknown_players: tuple[tuple[int, str], ...]
    summary: str


def canonical_id(snap: Snapshot, espn_player_id: int, name: str) -> str:
    for p in snap.players:
        if p.espn_id == espn_player_id:
            return p.player_id
    return f"espn:{espn_player_id}"


def _espn_to_canonical(snap: Snapshot) -> dict[int, str]:
    return {p.espn_id: p.player_id for p in snap.players if p.espn_id}


def _transaction_refs(league: EspnLeague) -> dict[tuple[str, int, int], str]:
    """(ADD|DROP, espn_player_id, team_id) -> transaction id, for executed roster moves."""
    refs: dict[tuple[str, int, int], str] = {}
    for tx in league.transactions:
        if not tx.is_roster_move:
            continue
        for it in tx.items:
            if it.kind == "ADD":
                refs[("ADD", it.espn_player_id, it.to_team_id)] = tx.transaction_id
            elif it.kind == "DROP":
                refs[("DROP", it.espn_player_id, it.from_team_id)] = tx.transaction_id
            elif it.kind == "TRADE":
                refs[("ADD", it.espn_player_id, it.to_team_id)] = tx.transaction_id
                refs[("DROP", it.espn_player_id, it.from_team_id)] = tx.transaction_id
    return refs


def _diff_team(
    manager_id: str,
    team: EspnTeam,
    current: tuple[str, ...],
    by_espn: dict[int, str],
    refs: dict[tuple[str, int, int], str],
) -> tuple[RosterDiff | None, list[tuple[int, str]]]:
    unknown: list[tuple[int, str]] = []
    espn_roster: dict[str, int] = {}
    for e in team.roster:
        cid = by_espn.get(e.espn_player_id, f"espn:{e.espn_player_id}")
        if e.espn_player_id not in by_espn:
            unknown.append((e.espn_player_id, e.name))
        espn_roster[cid] = e.espn_player_id
    have = set(current)
    added = tuple(cid for cid in espn_roster if cid not in have)
    dropped = tuple(cid for cid in current if cid not in espn_roster)
    if not added and not dropped:
        return None, unknown
    canonical_to_espn = {v: k for k, v in by_espn.items()}
    sources = []
    for cid in added:
        key = ("ADD", espn_roster[cid], team.team_id)
        sources.append(f"espn:{refs[key]}" if key in refs else ROSTER_DIFF_REF)
    for cid in dropped:
        eid = canonical_to_espn.get(cid, int(cid.split(":")[1]) if cid.startswith("espn:") else -1)
        key = ("DROP", eid, team.team_id)
        sources.append(f"espn:{refs[key]}" if key in refs else ROSTER_DIFF_REF)
    return RosterDiff(manager_id, team.team_id, added, dropped, tuple(sources)), unknown


def _league_updated_event(state: DraftState, league: EspnLeague, mapping: dict[str, int]) -> tuple | None:
    cfg = state.league
    if cfg.espn_league_id == league.league_id and cfg.espn_team_ids == mapping:
        return None
    updated = cfg.model_copy(
        update={"espn_league_id": league.league_id, "espn_team_ids": dict(mapping), "espn_linked_at": league.fetched_at}
    )
    key = f"espn-link:{league.league_id}:{league.fetched_at}"
    return EventType.league_updated, {"league": updated.model_dump(mode="json")}, key


def plan_sync(state: DraftState, league: EspnLeague, snap: Snapshot, mapping: dict[str, int]) -> SyncPlan:
    by_espn = _espn_to_canonical(snap)
    refs = _transaction_refs(league)
    diffs: list[RosterDiff] = []
    unknown: list[tuple[int, str]] = []
    warnings: list[str] = []
    for mid, tid in mapping.items():
        try:
            team = league.team(tid)
        except KeyError:
            warnings.append(f"ESPN team {tid} (mapped to {mid}) is missing from the league payload")
            continue
        diff, unk = _diff_team(mid, team, state.current_roster(mid), by_espn, refs)
        unknown.extend(unk)
        if diff is not None:
            diffs.append(diff)
    for eid, name in unknown:
        warnings.append(f"{name} (ESPN {eid}) is not in the projection snapshot; kept as owned with no projection")
    events: list[tuple] = []
    link_ev = _league_updated_event(state, league, mapping)
    if link_ev is not None:
        events.append(link_ev)
    n_adds = sum(len(d.added) for d in diffs)
    n_drops = sum(len(d.dropped) for d in diffs)
    summary = f"ESPN sync: {n_adds} adds, {n_drops} drops across {len(diffs)} teams; {len(unknown)} unknown players"
    if diffs:
        payload = {
            "moves": [
                {
                    "manager_id": d.manager_id,
                    "added": list(d.added),
                    "dropped": list(d.dropped),
                    "source_ref": ",".join(sorted(set(d.source_refs))),
                }
                for d in diffs
            ],
            "effective_at": league.fetched_at,
            "note": summary,
        }
        events.append((EventType.roster_changed, payload, f"espn-sync:{league.league_id}:{league.fetched_at}"))
    return SyncPlan(
        fetched_at=league.fetched_at,
        diffs=tuple(diffs),
        events=tuple(events),
        warnings=tuple(warnings),
        unknown_players=tuple(unknown),
        summary=summary,
    )
