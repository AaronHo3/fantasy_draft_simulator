"""HTTP routes. Thin: validation + delegation to the store, registry and service."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.api import schemas as S
from app.api.deps import AppContext, get_context
from app.draft.events import DraftError, DraftState, EventType
from app.identity.players import normalize_name
from app.persistence.store import ConflictError
from app.projections.snapshot import Snapshot
from app.recommend import service as svc

router = APIRouter(prefix="/api")


def _error(status: int, code: str, message: str, **detail: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content=S.ErrorBody(code=code, message=message, detail=detail).model_dump())


def _session_or_404(ctx: AppContext, session_id: str) -> tuple[dict[str, Any], DraftState]:
    meta = ctx.store.session_meta(session_id)
    if meta is None:
        raise HTTPException(404, detail={"code": "no_session", "message": f"session {session_id} not found"})
    return meta, ctx.store.state(session_id)


def _snapshot_for(ctx: AppContext, meta: dict[str, Any]) -> Snapshot:
    sid = meta.get("snapshot_id")
    if sid and ctx.registry.has(sid):
        return ctx.registry.get(sid)
    return ctx.registry.get(ctx.registry.default_id())


def _snapshot_meta(s: Snapshot) -> S.SnapshotMeta:
    return S.SnapshotMeta(
        snapshot_id=s.snapshot_id,
        label=s.label,
        source=s.source,
        season=s.season,
        created_at=s.created_at,
        n_players=s.n,
        is_demo=s.is_demo,
        adp_platform=s.adp_platform,
        adp_asof=s.adp_asof,
        rank_source=s.rank_source,
        health=s.health,
        provenance=s.provenance,
    )


# --- health / snapshots -----------------------------------------------------------------------


@router.get("/health", response_model=S.HealthView)
def health(ctx: AppContext = Depends(get_context)) -> S.HealthView:
    data_health: dict[str, Any] = {}
    try:
        from app.sources.health import health_report  # optional module (data adapters)

        data_health = health_report(ctx.settings.data_dir)
    except Exception as e:  # noqa: BLE001 - adapters are optional
        data_health = {"status": "unavailable", "detail": str(e)}
    return S.HealthView(
        status="ok",
        data_dir=str(ctx.settings.data_dir),
        snapshots=[_snapshot_meta(s) for s in ctx.registry.list()],
        default_snapshot_id=ctx.registry.default_id(),
        snapshot_errors=ctx.registry.errors,
        sessions=len(ctx.store.list_sessions()),
        data_health=data_health,
    )


@router.get("/snapshots", response_model=list[S.SnapshotMeta])
def list_snapshots(ctx: AppContext = Depends(get_context)) -> list[S.SnapshotMeta]:
    return [_snapshot_meta(s) for s in ctx.registry.list()]


@router.get("/snapshots/{snapshot_id}/players", response_model=list[S.PlayerView])
def snapshot_players(
    snapshot_id: str,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=2000),
    session_id: str | None = None,
    ctx: AppContext = Depends(get_context),
) -> list[S.PlayerView]:
    if not ctx.registry.has(snapshot_id):
        raise HTTPException(404, detail={"code": "no_snapshot", "message": snapshot_id})
    snap = ctx.registry.get(snapshot_id)
    state = ctx.store.state(session_id) if session_id and ctx.store.session_meta(session_id) else None
    idxs = range(snap.n)
    if q:
        nq = normalize_name(q)
        toks = nq.split()
        idxs = [
            i
            for i, p in enumerate(snap.players)
            if all(any(t in key for key in p.search_keys) or (p.team and t == p.team.lower()) for t in toks)
        ]
        idxs = sorted(
            idxs,
            key=lambda i: (
                not any(k.startswith(nq) for k in snap.players[i].search_keys),
                snap.rank[i] if snap.rank[i] == snap.rank[i] else 1e9,
            ),
        )
    else:
        idxs = sorted(idxs, key=lambda i: snap.rank[i] if snap.rank[i] == snap.rank[i] else 1e9)
    return [svc.player_view(snap, i, state) for i in list(idxs)[:limit]]


# --- sessions ---------------------------------------------------------------------------------


@router.post("/sessions", response_model=S.SessionSummary, status_code=201)
def create_session(body: S.SessionCreate, ctx: AppContext = Depends(get_context)) -> S.SessionSummary:
    snapshot_id = body.snapshot_id or ctx.registry.default_id()
    if not ctx.registry.has(snapshot_id):
        raise HTTPException(404, detail={"code": "no_snapshot", "message": snapshot_id})
    sid = ctx.store.create_session(body.league, body.strategy, snapshot_id, body.name)
    meta = ctx.store.session_meta(sid)
    assert meta
    return S.SessionSummary(
        **{k: meta[k] for k in ("id", "name", "snapshot_id", "created_at", "updated_at")}, last_seq=1
    )


@router.get("/sessions", response_model=list[S.SessionSummary])
def list_sessions(ctx: AppContext = Depends(get_context)) -> list[S.SessionSummary]:
    return [S.SessionSummary(**r) for r in ctx.store.list_sessions()]


@router.get("/sessions/{session_id}", response_model=S.SessionDetail)
def get_session(session_id: str, ctx: AppContext = Depends(get_context)) -> S.SessionDetail:
    meta, state = _session_or_404(ctx, session_id)
    return S.SessionDetail(
        meta=S.SessionSummary(
            **{k: meta[k] for k in ("id", "name", "snapshot_id", "created_at", "updated_at")}, last_seq=state.last_seq
        ),
        state=svc.state_view(state),
    )


@router.get("/sessions/{session_id}/state", response_model=S.DraftStateView)
def get_state(session_id: str, ctx: AppContext = Depends(get_context)) -> S.DraftStateView:
    _, state = _session_or_404(ctx, session_id)
    return svc.state_view(state)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, ctx: AppContext = Depends(get_context)) -> None:
    _session_or_404(ctx, session_id)
    ctx.store.delete_session(session_id)


@router.get("/sessions/{session_id}/export")
def export_session(session_id: str, ctx: AppContext = Depends(get_context)) -> dict[str, Any]:
    _session_or_404(ctx, session_id)
    return ctx.store.export_session(session_id)


@router.post("/sessions/import", response_model=S.SessionSummary, status_code=201)
def import_session(body: dict[str, Any], ctx: AppContext = Depends(get_context)):
    try:
        sid = ctx.store.import_session(body)
    except DraftError as e:
        return _error(422, e.code, e.message, **e.detail)
    except (KeyError, ValueError) as e:
        return _error(422, "invalid_export", f"invalid export file: {e}")
    meta = ctx.store.session_meta(sid)
    assert meta
    return S.SessionSummary(
        **{k: meta[k] for k in ("id", "name", "snapshot_id", "created_at", "updated_at")},
        last_seq=ctx.store.state(sid).last_seq,
    )


@router.get("/sessions/{session_id}/events", response_model=list[S.EventView])
def list_events(session_id: str, ctx: AppContext = Depends(get_context)) -> list[S.EventView]:
    _session_or_404(ctx, session_id)
    return [S.EventView(**e.to_dict()) for e in ctx.store.events(session_id)]


@router.post("/sessions/{session_id}/events", response_model=S.EventResponse)
def append_event(session_id: str, body: S.EventRequest, ctx: AppContext = Depends(get_context)):
    _session_or_404(ctx, session_id)
    if body.type == EventType.session_created:
        return _error(422, "reserved_event", "session_created is reserved")
    try:
        ev, state, dedup = ctx.store.append(
            session_id, body.type, body.payload, body.idempotency_key, body.expected_revision, body.source
        )
    except ConflictError as e:
        return _error(409, "revision_conflict", str(e), expected=e.expected, actual=e.actual)
    except DraftError as e:
        return _error(422, e.code, e.message, **e.detail)
    except ValueError as e:  # pydantic validation inside payloads
        return _error(422, "invalid_payload", str(e))
    return S.EventResponse(event=S.EventView(**ev.to_dict()), state=svc.state_view(state), deduplicated=dedup)


@router.post("/sessions/{session_id}/events/batch", response_model=S.DraftStateView)
def append_batch(session_id: str, body: S.BatchRequest, ctx: AppContext = Depends(get_context)):
    _session_or_404(ctx, session_id)
    try:
        state = ctx.store.append_batch(
            session_id,
            [(i.type, i.payload, i.idempotency_key) for i in body.items],
            body.expected_revision,
            body.source,
        )
    except ConflictError as e:
        return _error(409, "revision_conflict", str(e), expected=e.expected, actual=e.actual)
    except DraftError as e:
        return _error(422, e.code, e.message, **e.detail)
    return svc.state_view(state)


# --- imports ------------------------------------------------------------------------------------


@router.get("/templates/{kind}")
def template(kind: str, ctx: AppContext = Depends(get_context)):
    from fastapi.responses import PlainTextResponse

    from app.imports.csv_import import template_text

    if kind not in ("projections", "eligibility", "adp", "picks"):
        raise HTTPException(404, detail={"code": "no_template", "message": kind})
    try:
        return PlainTextResponse(template_text(kind), media_type="text/csv")
    except FileNotFoundError:
        raise HTTPException(
            404, detail={"code": "no_template", "message": f"template file for {kind} missing"}
        ) from None


def _preview(kind: str, text: str, snap: Snapshot, state: DraftState):
    from app.imports import csv_import as ci

    if kind == "projections":
        return ci.preview_projections(text, snap)
    if kind == "eligibility":
        return ci.preview_eligibility(text, snap)
    if kind == "adp":
        return ci.preview_adp(text, snap)
    return ci.preview_picks(
        text, snap, [m.id for m in state.league.managers], {m.id: m.name for m in state.league.managers}
    )


@router.post("/sessions/{session_id}/import/preview", response_model=S.ImportPreviewView)
def import_preview(session_id: str, body: S.ImportPreviewRequest, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    snap = _snapshot_for(ctx, meta)
    return S.ImportPreviewView(**_preview(body.kind, body.text, snap, state).to_dict())


@router.post("/sessions/{session_id}/import/apply", response_model=S.ImportApplyResponse)
def import_apply(session_id: str, body: S.ImportApplyRequest, ctx: AppContext = Depends(get_context)):
    from app.imports import csv_import as ci

    meta, state = _session_or_404(ctx, session_id)
    snap = _snapshot_for(ctx, meta)
    pv = _preview(body.kind, body.text, snap, state)
    if pv.missing_columns:
        return _error(422, "missing_columns", f"missing columns {list(pv.missing_columns)}")
    if pv.n_error and not body.skip_error_rows:
        return _error(
            422,
            "rows_with_errors",
            f"{pv.n_error} rows have errors; fix them or set skip_error_rows",
            rows=[r.row for r in pv.rows if not r.ok],
        )
    if body.kind == "picks":
        payloads = ci.picks_to_events(pv)
        try:
            new_state = ctx.store.append_batch(
                session_id,
                [(EventType.pick_committed, p, None) for p in payloads],
                body.expected_revision,
                source="import",
            )
        except ConflictError as e:
            return _error(409, "revision_conflict", str(e), expected=e.expected, actual=e.actual)
        except DraftError as e:
            return _error(422, e.code, e.message, **e.detail)
        return S.ImportApplyResponse(
            kind="picks", applied_rows=len(payloads), skipped_rows=pv.n_error, state=svc.state_view(new_state)
        )
    try:
        new_snap = {"projections": ci.apply_projections, "eligibility": ci.apply_eligibility, "adp": ci.apply_adp}[
            body.kind
        ](pv, snap)
    except ValueError as e:
        return _error(422, "incoherent_import", str(e))
    ctx.registry.register(new_snap)
    try:
        target = ctx.settings.snapshots_dir if not new_snap.is_demo else ctx.settings.data_dir / "demo" / "derived"
        new_snap.save(target / new_snap.snapshot_id)
    except OSError as e:  # keep working in memory even if the disk write fails
        import logging

        logging.getLogger(__name__).warning("could not persist derived snapshot: %s", e)
    ctx.store.set_snapshot(session_id, new_snap.snapshot_id)
    return S.ImportApplyResponse(
        kind=body.kind, applied_rows=pv.n_ok, skipped_rows=pv.n_error, snapshot_id=new_snap.snapshot_id
    )


# --- recommendations ----------------------------------------------------------------------------


@router.post("/sessions/{session_id}/recommend/fast", response_model=S.RecommendationResponse)
def recommend_fast(session_id: str, body: S.FastRecommendRequest, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    snap = _snapshot_for(ctx, meta)
    return svc.fast_recommendation(snap, state, body, ctx.settings.default_seed)


@router.get("/sessions/{session_id}/profiles", response_model=S.LeagueProfilesResponse)
def league_profiles(session_id: str, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    snap = _snapshot_for(ctx, meta)
    return svc.league_profiles(snap, state, ctx.settings.default_seed)


@router.post("/sessions/{session_id}/compare", response_model=S.CompareResponse)
def compare(session_id: str, body: S.CompareRequest, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    snap = _snapshot_for(ctx, meta)
    try:
        return svc.compare_players(snap, state, body.player_ids, ctx.settings.default_seed)
    except KeyError as e:
        return _error(404, "no_player", f"player {e} not in snapshot")


@router.post("/sessions/{session_id}/recommend/refine", response_model=S.JobAccepted, status_code=202)
def recommend_refine(session_id: str, body: S.RefineRequest, ctx: AppContext = Depends(get_context)):
    meta, state = _session_or_404(ctx, session_id)
    snap = _snapshot_for(ctx, meta)
    seed = body.seed if body.seed is not None else ctx.settings.default_seed
    ids = svc.response_ids(state, snap, seed)
    try:
        from app.recommend.refine import run_refinement
    except ImportError:
        return _error(501, "refine_unavailable", "refinement layers are not available in this build")

    def work():
        return run_refinement(snap, state, body, seed)

    job = ctx.jobs.submit(work, ids.model_dump())
    return S.JobAccepted(job_id=job.id, ids=ids, status=job.status)


@router.post("/sessions/{session_id}/punt-advisor", response_model=S.PuntAdvisorResponse)
def punt_advisor(session_id: str, body: S.PuntAdvisorRequest, ctx: AppContext = Depends(get_context)):
    """Compares strategy scenarios for the current roster. Synchronous, bounded by budget_ms; never applies anything."""
    from app.recommend.punt_advisor import analyze_punts

    meta, state = _session_or_404(ctx, session_id)
    snap = _snapshot_for(ctx, meta)
    seed = body.seed if body.seed is not None else ctx.settings.default_seed
    return analyze_punts(snap, state, body.budget_ms, seed)


@router.get("/jobs/{job_id}", response_model=S.JobView)
def get_job(job_id: str, session_id: str | None = None, ctx: AppContext = Depends(get_context)):
    job = ctx.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail={"code": "no_job", "message": job_id})
    stale = False
    if session_id and ctx.store.session_meta(session_id):
        st = ctx.store.state(session_id)
        stale = (
            job.ids.get("draft_revision") != st.draft_revision
            or job.ids.get("strategy_revision") != st.strategy_revision
            or job.ids.get("league_revision") != st.league_revision
        )
    result = job.result
    if result is not None and hasattr(result, "model_dump"):
        result = result.model_dump()
    return S.JobView(
        job_id=job.id,
        status=job.status,
        ids=job.ids,
        stale=stale,
        result=None if stale else result,
        error=job.error,
        elapsed_ms=job.elapsed_ms,
    )
