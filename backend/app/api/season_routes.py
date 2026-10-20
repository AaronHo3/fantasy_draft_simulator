"""ESPN link/sync and season read routes. Thin wrappers over ``app.season.service``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api import schemas as S
from app.api.deps import AppContext, get_context
from app.api.routes import _error
from app.season import service as season
from app.season.service import SeasonError

router = APIRouter(prefix="/api")


def _run(fn, *args):
    try:
        return fn(*args)
    except SeasonError as e:
        return _error(e.status, e.code, e.message, **e.detail)


@router.post("/sessions/{session_id}/espn/link", response_model=S.LinkPreview)
def link_preview(session_id: str, body: S.LinkRequest, ctx: AppContext = Depends(get_context)):
    return _run(season.link_preview, ctx, session_id, body.league_id, body.overrides)


@router.post("/sessions/{session_id}/espn/link/apply", response_model=S.SessionDetail)
def link_apply(session_id: str, body: S.LinkApplyRequest, ctx: AppContext = Depends(get_context)):
    return _run(season.link_apply, ctx, session_id, body.league_id, body.mapping)


@router.post("/sessions/{session_id}/espn/sync", response_model=S.SyncResult)
def sync(session_id: str, body: S.SyncRequest, ctx: AppContext = Depends(get_context)):
    return _run(season.run_sync, ctx, session_id, body.expected_revision)


@router.get("/sessions/{session_id}/season/overview", response_model=S.SeasonOverview)
def season_overview(
    session_id: str,
    seed: int | None = None,
    period: int | None = Query(default=None, ge=1, le=22),
    ctx: AppContext = Depends(get_context),
):
    return _run(season.overview, ctx, session_id, seed, period)


@router.get("/sessions/{session_id}/season/matchup", response_model=S.MatchupResponse)
def season_matchup(
    session_id: str,
    period: int = Query(ge=1, le=22),
    team_a: str = Query(min_length=1),
    team_b: str = Query(min_length=1),
    seed: int | None = None,
    ctx: AppContext = Depends(get_context),
):
    return _run(season.matchup, ctx, session_id, period, team_a, team_b, seed)


@router.get("/sessions/{session_id}/season/free-agents", response_model=S.FreeAgentsResponse)
def season_free_agents(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    position: str | None = None,
    q: str | None = None,
    ctx: AppContext = Depends(get_context),
):
    return _run(season.free_agents, ctx, session_id, limit, position, q)


@router.get("/sessions/{session_id}/season/results", response_model=S.WeekResultsResponse)
def season_results(
    session_id: str, period: int = Query(ge=1, le=22), seed: int | None = None, ctx: AppContext = Depends(get_context)
):
    return _run(season.results, ctx, session_id, period, seed)


@router.get("/sessions/{session_id}/season/predictions", response_model=S.PredictionsResponse)
def season_predictions(session_id: str, ctx: AppContext = Depends(get_context)):
    return _run(season.predictions, ctx, session_id)
