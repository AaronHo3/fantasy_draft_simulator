"""ESPN league link and sync routes (the only handlers that reach the network, and only on demand)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from app.api import schemas as S
from app.api.deps import AppContext, get_context
from app.api.routes import _error, _session_or_404, _snapshot_for
from app.draft.events import DraftError, DraftState, EventType, now_iso
from app.league.config import espn_season_id
from app.persistence.store import ConflictError
from app.recommend import service as svc
from app.season.link import match_teams
from app.season.live_status import write_live_status
from app.season.sync import SyncPlan, plan_sync
from app.sources.base import FetchError, SchemaError
from app.sources.espn_league import EspnLeague, LeagueAccessError, settings_diff

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

PRIVATE_HELP = (
    "ESPN league {league_id} is private. In ESPN: League > Settings > Basic Settings > "
    "Make League Viewable to Public (or add cookies to backend/.env)."
)


def _fetch_league(ctx: AppContext, league_id: int, season: str) -> tuple[EspnLeague, dict[str, Any]] | Any:
    """Returns (league, raw) or an error response."""
    try:
        league, raw = ctx.espn_fetch_league(league_id, espn_season_id(season))
    except LeagueAccessError:
        return _error(409, "league_private", PRIVATE_HELP.format(league_id=league_id))
    except (httpx.HTTPError, FetchError, SchemaError) as e:
        return _error(502, "espn_unavailable", f"ESPN did not answer: {e}")
    ctx.leagues[league_id] = league
    return league, raw


def _team_views(league: EspnLeague) -> list[S.EspnTeamView]:
    return [
        S.EspnTeamView(team_id=t.team_id, name=t.name, owner_name=t.owner_name, n_players=len(t.roster))
        for t in league.teams
    ]


@router.post("/sessions/{session_id}/espn/link", response_model=S.LinkPreview)
def link_preview(session_id: str, body: S.LinkRequest, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    got = _fetch_league(ctx, body.league_id, state.league.season)
    if not isinstance(got, tuple):
        return got
    league, _ = got
    snap = _snapshot_for(ctx, meta)
    mapping = match_teams(state, league, snap, body.overrides or None)
    names = {m.id: m.name for m in state.league.managers}
    teams = {t.team_id: t for t in league.teams}
    return S.LinkPreview(
        league_id=body.league_id,
        league_name=league.settings.name,
        teams=_team_views(league),
        mapping=[
            S.TeamMatchView(
                manager_id=m.manager_id,
                manager_name=names[m.manager_id],
                team_id=m.team_id,
                team_name=teams[m.team_id].name,
                owner_name=teams[m.team_id].owner_name,
                overlap=round(m.overlap, 3),
                confidence=m.confidence,
            )
            for m in mapping.matches
        ],
        unmatched_managers=list(mapping.unmatched_managers),
        unmatched_teams=list(mapping.unmatched_teams),
        settings_warnings=settings_diff(league.settings, state.league),
        warnings=list(mapping.warnings),
    )


@router.post("/sessions/{session_id}/espn/link/apply", response_model=S.SessionDetail)
def link_apply(session_id: str, body: S.LinkApplyRequest, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    updated = state.league.model_copy(
        update={"espn_league_id": body.league_id, "espn_team_ids": dict(body.mapping), "espn_linked_at": now_iso()}
    )
    try:
        _, new_state, _ = ctx.store.append(
            session_id, EventType.league_updated, {"league": updated.model_dump(mode="json")}, source="espn"
        )
    except (DraftError, ValueError) as e:
        return _error(422, "invalid_link", str(e))
    meta = ctx.store.session_meta(session_id) or meta
    return S.SessionDetail(meta=S.SessionSummary(**meta), state=svc.state_view(new_state))


def _refresh_players(ctx: AppContext, league_id: int, season: str, warnings: list[str]) -> None:
    try:
        frame = ctx.espn_fetch_players(espn_season_id(season))
        write_live_status(ctx.settings.live_dir, league_id, frame)
        ctx.invalidate_live_status(league_id)
    except Exception as e:  # noqa: BLE001 - live status is best effort; the sync itself still completes
        log.warning("ESPN player status refresh failed: %s", e)
        warnings.append(f"live player status not refreshed ({e}); using the snapshot's status")


def _apply_plan(ctx: AppContext, session_id: str, plan: SyncPlan, expected: int | None) -> DraftState | Any:
    if not plan.events:
        return ctx.store.state(session_id)
    try:
        return ctx.store.append_batch(session_id, list(plan.events), expected, source="espn")
    except ConflictError as e:
        return _error(409, "revision_conflict", str(e), expected=e.expected, actual=e.actual)
    except DraftError as e:
        return _error(422, e.code, e.message, **e.detail)


@router.post("/sessions/{session_id}/espn/sync", response_model=S.SyncResult)
def sync(session_id: str, body: S.SyncRequest, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    league_id = state.league.espn_league_id
    if league_id is None or not state.league.espn_team_ids:
        return _error(409, "not_linked", "link this session to an ESPN league first")
    if body.expected_revision is not None and body.expected_revision != state.last_seq:
        return _error(
            409, "revision_conflict", "stale revision", expected=body.expected_revision, actual=state.last_seq
        )
    got = _fetch_league(ctx, league_id, state.league.season)
    if not isinstance(got, tuple):
        return got
    league, _ = got
    snap = _snapshot_for(ctx, meta)
    plan = plan_sync(state, league, snap, state.league.espn_team_ids)
    new_state = _apply_plan(ctx, session_id, plan, body.expected_revision)
    if not isinstance(new_state, DraftState):
        return new_state
    warnings = list(plan.warnings) + settings_diff(league.settings, state.league)
    _refresh_players(ctx, league_id, state.league.season, warnings)
    ctx.store.set_sync(
        session_id,
        {
            "league_id": league_id,
            "fetched_at": league.fetched_at,
            "summary": plan.summary,
            "warnings": warnings,
            "changes": [
                d.__dict__ | {"added": list(d.added), "dropped": list(d.dropped), "source_refs": list(d.source_refs)}
                for d in plan.diffs
            ],
            "power": None,
            "current_period": league.settings.current_matchup_period,
        },
    )
    return S.SyncResult(
        ids=svc.response_ids(new_state, snap, ctx.settings.default_seed),
        fetched_at=league.fetched_at,
        summary=plan.summary,
        changes=[
            S.RosterDiffView(
                manager_id=d.manager_id,
                team_id=d.team_id,
                added=list(d.added),
                dropped=list(d.dropped),
                source_refs=list(d.source_refs),
            )
            for d in plan.diffs
        ],
        warnings=warnings,
        unknown_players=[S.UnknownPlayerView(espn_id=e, name=n) for e, n in plan.unknown_players],
        state=svc.state_view(new_state),
    )
