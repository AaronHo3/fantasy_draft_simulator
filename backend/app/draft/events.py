"""Append-only draft events and pure state replay.

State is always derived by replaying the committed event history. Nothing mutates a state object;
``apply`` returns a new ``DraftState``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.draft.schedule import Pick, build_pick_schedule, next_pick_for_manager, picks_between
from app.league.config import Keeper, LeagueConfig
from app.league.strategy import Strategy

SCHEMA_VERSION = 1


class EventType(StrEnum):
    session_created = "session_created"
    pick_committed = "pick_committed"
    pick_undone = "pick_undone"
    pick_corrected = "pick_corrected"
    keeper_assigned = "keeper_assigned"
    order_changed = "order_changed"
    strategy_changed = "strategy_changed"
    league_updated = "league_updated"
    format_confirmed = "format_confirmed"
    note = "note"
    roster_changed = "roster_changed"  # post-draft adds/drops/trades (ESPN sync or manual)


DRAFT_EVENTS = {
    EventType.pick_committed,
    EventType.pick_undone,
    EventType.pick_corrected,
    EventType.keeper_assigned,
    EventType.order_changed,
    EventType.league_updated,
}


class DraftError(ValueError):
    def __init__(self, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class Event:
    seq: int
    type: EventType
    payload: dict[str, Any]
    idempotency_key: str
    created_at: str
    source: str = "manual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "type": self.type.value,
            "payload": self.payload,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "source": self.source,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Event:
        return Event(
            int(d["seq"]),
            EventType(d["type"]),
            dict(d["payload"]),
            d["idempotency_key"],
            d["created_at"],
            d.get("source", "manual"),
        )


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class PickRecord:
    overall: int
    manager_id: str
    player_id: str
    is_keeper: bool = False
    source: str = "manual"
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "manager_id": self.manager_id,
            "player_id": self.player_id,
            "is_keeper": self.is_keeper,
            "source": self.source,
            "seq": self.seq,
        }


@dataclass(frozen=True)
class RosterMove:
    """One manager's adds and drops from a single ``roster_changed`` event."""

    manager_id: str
    added: tuple[str, ...]
    dropped: tuple[str, ...]
    source_ref: str
    seq: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "manager_id": self.manager_id,
            "added": list(self.added),
            "dropped": list(self.dropped),
            "source_ref": self.source_ref,
            "seq": self.seq,
        }


@dataclass(frozen=True)
class DraftState:
    league: LeagueConfig
    strategy: Strategy
    schedule: tuple[Pick, ...]
    picks: dict[int, PickRecord] = field(default_factory=dict)
    order_overrides: dict[int, str] = field(default_factory=dict)
    draft_revision: int = 0
    strategy_revision: int = 0
    league_revision: int = 0
    last_seq: int = 0
    warnings: tuple[str, ...] = ()
    moves: tuple[RosterMove, ...] = ()  # post-draft roster moves in event order

    # --- derived -------------------------------------------------------------------------
    @property
    def drafted_player_ids(self) -> frozenset[str]:
        return frozenset(p.player_id for p in self.picks.values())

    @property
    def has_roster_moves(self) -> bool:
        return bool(self.moves)

    def current_roster(self, manager_id: str) -> tuple[str, ...]:
        """Draft picks in pick order, minus drops, plus adds in event order (post-draft truth)."""
        roster = [r.player_id for r in self.roster(manager_id)]
        for mv in self.moves:
            if mv.manager_id != manager_id:
                continue
            roster = [p for p in roster if p not in mv.dropped]
            roster.extend(mv.added)
        return tuple(roster)

    def current_rosters(self) -> dict[str, tuple[str, ...]]:
        return {m.id: self.current_roster(m.id) for m in self.league.managers}

    @property
    def owned_player_ids(self) -> frozenset[str]:
        return frozenset(p for roster in self.current_rosters().values() for p in roster)

    @property
    def current_pick(self) -> Pick | None:
        for p in self.schedule:
            if p.overall not in self.picks:
                return p
        return None

    @property
    def is_complete(self) -> bool:
        return self.current_pick is None

    @property
    def on_clock_manager_id(self) -> str | None:
        cp = self.current_pick
        return cp.manager_id if cp else None

    def roster(self, manager_id: str) -> list[PickRecord]:
        return sorted((p for p in self.picks.values() if p.manager_id == manager_id), key=lambda r: r.overall)

    def rosters(self) -> dict[str, list[PickRecord]]:
        return {m.id: self.roster(m.id) for m in self.league.managers}

    def user_next_pick(self) -> Pick | None:
        cp = self.current_pick
        if cp is None:
            return None
        if cp.manager_id == self.league.user_manager_id:
            return cp
        return next_pick_for_manager(list(self.schedule), self.league.user_manager_id, cp.overall - 1)

    def user_following_pick(self) -> Pick | None:
        """The user's pick after the next one (for draft-now-vs-wait)."""
        nxt = self.user_next_pick()
        if nxt is None:
            return None
        return next_pick_for_manager(list(self.schedule), self.league.user_manager_id, nxt.overall)

    def picks_until_user_turn(self) -> int | None:
        cp, nxt = self.current_pick, self.user_next_pick()
        if cp is None or nxt is None:
            return None
        return picks_between(cp.overall - 1, nxt.overall)

    def remaining_picks_for(self, manager_id: str) -> int:
        return sum(1 for p in self.schedule if p.manager_id == manager_id and p.overall not in self.picks)

    def last_committed_overall(self) -> int | None:
        xs = [o for o, r in self.picks.items() if not r.is_keeper]
        return max(xs) if xs else None


# --- construction / replay -------------------------------------------------------------------


def initial_state(league: LeagueConfig, strategy: Strategy | None = None) -> DraftState:
    schedule = tuple(build_pick_schedule(league))
    picks = {
        p.overall: PickRecord(p.overall, p.manager_id, p.keeper_player_id, True, "keeper")
        for p in schedule
        if p.keeper_player_id
    }
    return DraftState(league, strategy or Strategy(), schedule, picks)


def replay(league: LeagueConfig, events: list[Event], strategy: Strategy | None = None) -> DraftState:
    state = initial_state(league, strategy)
    for ev in events:
        state = apply(state, ev)
    return state


def _rebuild_schedule(state: DraftState, league: LeagueConfig, overrides: dict[int, str]) -> DraftState:
    schedule = tuple(build_pick_schedule(league, overrides))
    warnings: list[str] = []
    picks = dict(state.picks)
    # keepers from the league config
    for p in schedule:
        if p.keeper_player_id and p.overall not in picks:
            picks[p.overall] = PickRecord(p.overall, p.manager_id, p.keeper_player_id, True, "keeper")
    by_overall = {p.overall: p for p in schedule}
    for o, rec in list(picks.items()):
        sp = by_overall.get(o)
        if sp is None:
            warnings.append(f"pick {o} ({rec.player_id}) is beyond the new schedule length; kept")
        elif sp.manager_id != rec.manager_id:
            warnings.append(
                f"pick {o}: recorded for {rec.manager_id} but schedule now says "
                f"{sp.manager_id}; kept as recorded, review it"
            )
    return replace(
        state, league=league, schedule=schedule, picks=picks, order_overrides=dict(overrides), warnings=tuple(warnings)
    )


def apply(state: DraftState, ev: Event) -> DraftState:  # noqa: C901 - explicit dispatch
    t, p = ev.type, ev.payload
    base = replace(state, last_seq=ev.seq)
    if t == EventType.session_created or t == EventType.note:
        return base
    if t == EventType.format_confirmed:
        league = state.league.model_copy(update={"format_confirmed": True})
        return replace(base, league=league, league_revision=ev.seq)
    if t == EventType.strategy_changed:
        return replace(base, strategy=Strategy.model_validate(p["strategy"]), strategy_revision=ev.seq)
    if t == EventType.league_updated:
        league = LeagueConfig.model_validate(p["league"])
        new = _rebuild_schedule(base, league, state.order_overrides)
        return replace(new, draft_revision=ev.seq, league_revision=ev.seq)
    if t == EventType.order_changed:
        overrides = {int(k): str(v) for k, v in p["overrides"].items()}
        new = _rebuild_schedule(base, state.league, overrides)
        return replace(new, draft_revision=ev.seq)
    if t == EventType.keeper_assigned:
        keeper = Keeper(manager_id=p["manager_id"], player_id=p["player_id"], round=int(p["round"]))
        if keeper.player_id in state.drafted_player_ids:
            raise DraftError("duplicate_player", f"{keeper.player_id} is already drafted")
        league = state.league.model_copy(update={"keepers": [*state.league.keepers, keeper]})
        new = _rebuild_schedule(base, league, state.order_overrides)
        return replace(new, draft_revision=ev.seq, league_revision=ev.seq)
    if t == EventType.pick_committed:
        return replace(_commit(state, p, ev), last_seq=ev.seq, draft_revision=ev.seq)
    if t == EventType.pick_undone:
        _require_unlocked(state)
        return replace(_undo(state, p), last_seq=ev.seq, draft_revision=ev.seq)
    if t == EventType.pick_corrected:
        _require_unlocked(state)
        return replace(_correct(state, p, ev), last_seq=ev.seq, draft_revision=ev.seq)
    if t == EventType.roster_changed:
        return replace(_roster_changed(state, p, ev), last_seq=ev.seq, draft_revision=ev.seq)
    raise DraftError("unknown_event", f"unknown event type {t}")


def _require_unlocked(state: DraftState) -> None:
    if state.has_roster_moves:
        raise DraftError("draft_locked", "the draft record is locked once post-draft roster changes exist")


def _parse_moves(p: dict[str, Any], seq: int) -> tuple[RosterMove, ...]:
    moves = []
    for raw in p.get("moves", []):
        moves.append(
            RosterMove(
                manager_id=str(raw["manager_id"]),
                added=tuple(str(x) for x in raw.get("added", [])),
                dropped=tuple(str(x) for x in raw.get("dropped", [])),
                source_ref=str(raw.get("source_ref", "manual")),
                seq=seq,
            )
        )
    return tuple(moves)


def _roster_changed(state: DraftState, p: dict[str, Any], ev: Event) -> DraftState:
    """All drops first, then all adds, so a trade is one atomic event."""
    if not state.is_complete:
        raise DraftError("draft_incomplete", "roster changes are only recorded after the draft is complete")
    moves = _parse_moves(p, ev.seq)
    rosters = {m: set(r) for m, r in state.current_rosters().items()}
    for mv in moves:
        if mv.manager_id not in rosters:
            raise DraftError("unknown_manager", f"unknown manager {mv.manager_id}")
        missing = [x for x in mv.dropped if x not in rosters[mv.manager_id]]
        if missing:
            raise DraftError("roster_conflict", f"{mv.manager_id} does not own {missing}", manager_id=mv.manager_id)
        rosters[mv.manager_id] -= set(mv.dropped)
    for mv in moves:
        owned_by = {pid: m for m, r in rosters.items() for pid in r}
        taken = [x for x in mv.added if x in owned_by]
        if taken:
            owner = owned_by[taken[0]]
            raise DraftError("roster_conflict", f"{taken} already owned by {owner}", manager_id=mv.manager_id)
        rosters[mv.manager_id] |= set(mv.added)
    return replace(state, moves=(*state.moves, *moves))


def _commit(state: DraftState, p: dict[str, Any], ev: Event) -> DraftState:
    cp = state.current_pick
    if cp is None:
        raise DraftError("draft_complete", "the draft is complete")
    overall = int(p.get("overall", cp.overall))
    if overall != cp.overall:
        raise DraftError(
            "not_on_clock", f"pick {overall} is not on the clock (current is {cp.overall})", current_overall=cp.overall
        )
    manager_id = p.get("manager_id") or cp.manager_id
    if manager_id != cp.manager_id:
        raise DraftError("wrong_manager", f"{cp.manager_id} is on the clock, not {manager_id}", on_clock=cp.manager_id)
    player_id = str(p["player_id"])
    if player_id in state.drafted_player_ids:
        raise DraftError("duplicate_player", f"{player_id} was already drafted")
    picks = dict(state.picks)
    picks[overall] = PickRecord(overall, manager_id, player_id, False, ev.source, ev.seq)
    return replace(state, picks=picks)


def _undo(state: DraftState, p: dict[str, Any]) -> DraftState:
    last = state.last_committed_overall()
    if last is None:
        raise DraftError("nothing_to_undo", "no committed picks to undo")
    overall = int(p.get("overall", last))
    if overall != last:
        raise DraftError(
            "not_last_pick",
            f"only the last pick ({last}) can be undone; use a correction for pick {overall}",
            last_overall=last,
        )
    picks = dict(state.picks)
    del picks[overall]
    return replace(state, picks=picks)


def _correct(state: DraftState, p: dict[str, Any], ev: Event) -> DraftState:
    overall = int(p["overall"])
    rec = state.picks.get(overall)
    if rec is None:
        raise DraftError("no_such_pick", f"pick {overall} has not been made")
    if rec.is_keeper:
        raise DraftError("keeper_pick", "keeper picks are changed through the league settings")
    player_id = str(p["player_id"])
    others = {o: r for o, r in state.picks.items() if o != overall}
    if any(r.player_id == player_id for r in others.values()):
        raise DraftError("duplicate_player", f"{player_id} is already drafted at another pick")
    picks = dict(state.picks)
    picks[overall] = PickRecord(overall, rec.manager_id, player_id, False, ev.source, ev.seq)
    return replace(state, picks=picks)
