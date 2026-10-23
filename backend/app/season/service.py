"""Season workflows shared by the HTTP routes and the CLI: link, sync, overview, free agents, results.

Only ``link_preview`` and ``run_sync`` reach the network (through the fetchers on the context); every
read function works from the stored state, the snapshot and the cached league payload.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.api import schemas as S
from app.api.deps import AppContext
from app.draft.events import DraftError, DraftState, EventType, now_iso
from app.league.config import espn_season_id
from app.persistence.store import ConflictError
from app.recommend import service as svc
from app.season.free_agents import free_agents as rank_free_agents
from app.season.link import match_teams
from app.season.live_status import status_overlay, write_live_status
from app.season.power import matchup_odds, power_rankings
from app.season.results import week_results
from app.season.sync import SyncPlan, plan_sync
from app.season.weeks import calendar_matches_espn, current_period, period_window
from app.sources.base import FetchError, SchemaError
from app.sources.espn_league import EspnLeague, LeagueAccessError, parse_league, settings_diff

log = logging.getLogger(__name__)

PRIVATE_HELP = (
    "ESPN league {league_id} is private. In ESPN: League > Settings > Basic Settings > "
    "Make League Viewable to Public, then sync again."
)


class SeasonError(Exception):
    def __init__(self, status: int, code: str, message: str, **detail: Any):
        super().__init__(message)
        self.status, self.code, self.message, self.detail = status, code, message, detail


# --- shared helpers -------------------------------------------------------------------------------


def _session(ctx: AppContext, session_id: str) -> tuple[dict[str, Any], DraftState]:
    meta = ctx.store.session_meta(session_id)
    if meta is None:
        raise SeasonError(404, "no_session", f"session {session_id} not found")
    return meta, ctx.store.state(session_id)


def _snapshot(ctx: AppContext, meta: dict[str, Any]):
    sid = meta.get("snapshot_id")
    if sid and ctx.registry.has(sid):
        return ctx.registry.get(sid)
    return ctx.registry.get(ctx.registry.default_id())


def _league_file(ctx: AppContext, league_id: int):
    return ctx.settings.live_dir / str(league_id) / "league.json"


def fetch_league(ctx: AppContext, league_id: int, season: str) -> EspnLeague:
    try:
        league, raw = ctx.espn_fetch_league(league_id, espn_season_id(season))
    except LeagueAccessError as e:
        raise SeasonError(409, "league_private", PRIVATE_HELP.format(league_id=league_id)) from e
    except (httpx.HTTPError, FetchError, SchemaError) as e:
        raise SeasonError(502, "espn_unavailable", f"ESPN did not answer: {e}") from e
    ctx.leagues[league_id] = league
    if raw:
        path = _league_file(ctx, league_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"fetched_at": league.fetched_at, "payload": raw}))
        os.replace(tmp, path)
    return league


def _file_fetched_at(path) -> str | None:
    """Cheap peek at the fetched_at of the payload on disk (the file starts with that key)."""
    try:
        with path.open() as fh:
            head = fh.read(200)
        return json.loads(head.split(', "payload"')[0] + "}").get("fetched_at")
    except (OSError, ValueError):
        return None


def cached_league(ctx: AppContext, league_id: int, season: str) -> EspnLeague | None:
    """The last synced league. Another process (the CLI, auto-refresh in a second server) may have
    synced since this one did, so the file wins whenever it is newer than the in-memory copy."""
    hit = ctx.leagues.get(league_id)
    path = _league_file(ctx, league_id)
    if not path.exists():
        return hit
    on_disk = _file_fetched_at(path)
    if hit is not None and (on_disk is None or on_disk <= hit.fetched_at):
        return hit
    try:
        doc = json.loads(path.read_text())
        league = parse_league(doc["payload"], league_id, espn_season_id(season), doc["fetched_at"])
    except (OSError, ValueError, KeyError, SchemaError) as e:
        log.warning("cached league payload unreadable: %s", e)
        return hit
    ctx.leagues[league_id] = league
    ctx.invalidate_live_status(league_id)
    return league


def _ir_ids(league: EspnLeague | None, snap) -> frozenset[str]:
    if league is None:
        return frozenset()
    by_espn = {p.espn_id: p.player_id for p in snap.players if p.espn_id}
    return frozenset(
        by_espn.get(e.espn_player_id, f"espn:{e.espn_player_id}") for t in league.teams for e in t.roster if e.on_ir
    )


def _team_to_manager(state: DraftState) -> dict[int, str]:
    return {tid: mid for mid, tid in state.league.espn_team_ids.items()}


# --- link ----------------------------------------------------------------------------------------


def link_preview(ctx: AppContext, session_id: str, league_id: int, overrides: dict[str, int] | None) -> S.LinkPreview:
    meta, state = _session(ctx, session_id)
    league = fetch_league(ctx, league_id, state.league.season)
    snap = _snapshot(ctx, meta)
    mapping = match_teams(state, league, snap, overrides or None)
    names = {m.id: m.name for m in state.league.managers}
    teams = {t.team_id: t for t in league.teams}
    return S.LinkPreview(
        league_id=league_id,
        league_name=league.settings.name,
        teams=[
            S.EspnTeamView(team_id=t.team_id, name=t.name, owner_name=t.owner_name, n_players=len(t.roster))
            for t in league.teams
        ],
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


def link_apply(ctx: AppContext, session_id: str, league_id: int, mapping: dict[str, int]) -> S.SessionDetail:
    meta, state = _session(ctx, session_id)
    updated = state.league.model_copy(
        update={"espn_league_id": league_id, "espn_team_ids": dict(mapping), "espn_linked_at": now_iso()}
    )
    try:
        _, new_state, _ = ctx.store.append(
            session_id, EventType.league_updated, {"league": updated.model_dump(mode="json")}, source="espn"
        )
    except (DraftError, ValueError) as e:
        raise SeasonError(422, "invalid_link", str(e)) from e
    meta = ctx.store.session_meta(session_id) or meta
    return S.SessionDetail(meta=S.SessionSummary(**meta), state=svc.state_view(new_state))


# --- sync ----------------------------------------------------------------------------------------


def _refresh_players(ctx: AppContext, league_id: int, season: str, warnings: list[str]) -> None:
    try:
        frame = ctx.espn_fetch_players(espn_season_id(season))
        write_live_status(ctx.settings.live_dir, league_id, frame)
        ctx.invalidate_live_status(league_id)
    except Exception as e:  # noqa: BLE001 - live status is best effort; the sync itself still completes
        log.warning("ESPN player status refresh failed: %s", e)
        warnings.append(f"live player status not refreshed ({e}); using the snapshot's status")


def _apply_plan(ctx: AppContext, session_id: str, plan: SyncPlan, expected: int | None) -> DraftState:
    if not plan.events:
        return ctx.store.state(session_id)
    try:
        return ctx.store.append_batch(session_id, list(plan.events), expected, source="espn")
    except ConflictError as e:
        raise SeasonError(409, "revision_conflict", str(e), expected=e.expected, actual=e.actual) from e
    except DraftError as e:
        raise SeasonError(422, e.code, e.message, **e.detail) from e


def _calendar_warning(season: str, league: EspnLeague, warnings: list[str]) -> None:
    final = league.settings.final_scoring_period
    try:
        ok = final == 0 or calendar_matches_espn(season, final)
    except ValueError:
        ok = False
    if not ok:
        warnings.append(
            f"ESPN's season ends on scoring period {final} but the app's week calendar does not; "
            "matchup-week game counts may be off (see app/season/weeks.py)"
        )


def _no_team_ids(ctx: AppContext, snap, league_id: int | None) -> frozenset[str]:
    status = status_overlay(snap, ctx.live_status(league_id) if league_id else None)
    return frozenset(pid for pid, s in status.items() if (s.get("injury_status") or "").upper() == "NO_TEAM")


def _team_schedule(ctx: AppContext, state: DraftState):
    sched = ctx.get_schedule()
    if sched is None or state.league.lineup_mode != "daily":
        return None
    return ctx.team_schedule()


def _power(ctx: AppContext, snap, state: DraftState, league: EspnLeague | None, seed: int):
    return power_rankings(
        snap,
        state,
        seed,
        _ir_ids(league, snap),
        unavailable=_no_team_ids(ctx, snap, state.league.espn_league_id),
        team_schedule=_team_schedule(ctx, state),
    )


def _power_rows(ctx: AppContext, snap, state: DraftState, league: EspnLeague | None) -> list[dict[str, Any]]:
    return [p.__dict__ for p in _power(ctx, snap, state, league, ctx.settings.default_seed)]


def run_sync(ctx: AppContext, session_id: str, expected_revision: int | None) -> S.SyncResult:
    meta, state = _session(ctx, session_id)
    league_id = state.league.espn_league_id
    if league_id is None or not state.league.espn_team_ids:
        raise SeasonError(409, "not_linked", "link this session to an ESPN league first")
    if expected_revision is not None and expected_revision != state.last_seq:
        raise SeasonError(409, "revision_conflict", "stale revision", expected=expected_revision, actual=state.last_seq)
    league = fetch_league(ctx, league_id, state.league.season)
    snap = _snapshot(ctx, meta)
    plan = plan_sync(state, league, snap, state.league.espn_team_ids)
    # The plan was built from ``state``; apply it only over that exact revision so a sync that
    # landed while we were talking to ESPN (auto-refresh vs. manual, CLI vs. UI) is rejected.
    new_state = _apply_plan(ctx, session_id, plan, state.last_seq)
    warnings = list(plan.warnings) + settings_diff(league.settings, state.league)
    _calendar_warning(state.league.season, league, warnings)
    _refresh_players(ctx, league_id, state.league.season, warnings)
    previous = ctx.store.get_sync(session_id) or {}
    roster_changed = any(t == EventType.roster_changed for t, _, _ in plan.events)
    period_now = league.settings.current_matchup_period or current_period(state.league.season, _today())
    pairs_now = _pairs(ctx, snap, new_state, league, period_now, ctx.settings.default_seed)
    if pairs_now:
        record_predictions(ctx, session_id, new_state, pairs_now, period_now)
    ctx.store.set_sync(
        session_id,
        {
            "league_id": league_id,
            "fetched_at": league.fetched_at,
            "summary": plan.summary,
            "warnings": warnings,
            "changes": [
                {
                    "manager_id": d.manager_id,
                    "team_id": d.team_id,
                    "added": list(d.added),
                    "dropped": list(d.dropped),
                    "source_refs": list(d.source_refs),
                }
                for d in plan.diffs
            ],
            "power": _power_rows(ctx, snap, new_state, league),
            # movement arrows compare with the table from the last sync that changed a roster
            "previous_power": previous.get("power") if roster_changed else previous.get("previous_power"),
            "current_period": league.settings.current_matchup_period or None,
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


# --- predictions log ------------------------------------------------------------------------------


def _today() -> date:
    """US calendar date (UTC minus 6 h, like the schedule model); patched in tests."""
    return (datetime.now(UTC) - timedelta(hours=6)).date()


def record_predictions(
    ctx: AppContext, session_id: str, state: DraftState, pairs: list[S.MatchupPairView], period: int
) -> None:
    """Write this period's projected winners. Once the period has started the rows are frozen."""
    try:
        started = _today() >= period_window(state.league.season, period)[0]
    except ValueError:
        started = False
    existing = {(r["period"], r["home_manager_id"]): r for r in ctx.store.predictions(session_id)}
    now = now_iso()
    for pair in pairs:
        prev = existing.get((period, pair.home_manager_id))
        if prev is not None and prev.get("locked"):
            continue
        if prev is not None and started:
            # the week began since the last write: freeze the last pre-week projection as it was
            ctx.store.upsert_prediction(session_id, period, pair.home_manager_id, {**prev, "locked": True})
            continue
        o = pair.odds
        if o is None:
            winner, p_winner, p_tie = None, None, None
        else:
            home_wins = o.p_win_a > o.p_win_b or (o.p_win_a == o.p_win_b and o.expected_a >= o.expected_b)
            winner = pair.home_manager_id if home_wins else pair.away_manager_id
            p_winner, p_tie = (o.p_win_a if home_wins else o.p_win_b), o.p_tie
        ctx.store.upsert_prediction(
            session_id,
            period,
            pair.home_manager_id,
            {
                "period": period,
                "home_manager_id": pair.home_manager_id,
                "away_manager_id": pair.away_manager_id,
                "predicted_winner": winner,
                "p_winner": p_winner,
                "p_tie": p_tie,
                "expected_home": o.expected_a if o else None,
                "expected_away": o.expected_b if o else None,
                "locked": started,
                "predicted_at": now,
            },
        )


def _actual_winner(
    league: EspnLeague | None, state: DraftState, rec: dict[str, Any]
) -> tuple[str | None, dict[str, float] | None]:
    """ESPN's decided result for a prediction row: (winner id | 'tie' | None, cats by manager)."""
    if league is None or rec.get("away_manager_id") is None:
        return None, None
    t2m = _team_to_manager(state)
    for r in week_results(league, int(rec["period"]), t2m, state.league.categories):
        if r.away is None or r.home.manager_id != rec["home_manager_id"]:
            continue
        cats = {r.home.manager_id: r.home.cats_won, r.away.manager_id: r.away.cats_won}
        try:
            over = _today() > period_window(state.league.season, int(rec["period"]))[1]
        except ValueError:
            over = False
        if r.winner in ("HOME", "AWAY", "TIE"):
            winner = {"HOME": r.home.manager_id, "AWAY": r.away.manager_id, "TIE": "tie"}[r.winner]
        elif over:
            winner = (
                r.home.manager_id
                if r.home.cats_won > r.away.cats_won
                else r.away.manager_id
                if r.away.cats_won > r.home.cats_won
                else "tie"
            )
        else:
            return None, cats
        return winner, cats
    return None, None


def predictions(ctx: AppContext, session_id: str) -> S.PredictionsResponse:
    meta, state = _session(ctx, session_id)
    snap = _snapshot(ctx, meta)
    league_id = state.league.espn_league_id
    league = cached_league(ctx, league_id, state.league.season) if league_id else None
    rows: list[S.PredictionView] = []
    decided = correct = 0
    brier_sum = 0.0
    by_period: dict[str, dict[str, int]] = {}
    for rec in ctx.store.predictions(session_id):
        winner, cats = _actual_winner(league, state, rec)
        is_correct = None
        if winner is not None and rec.get("predicted_winner") is not None:
            is_correct = winner == rec["predicted_winner"]
            decided += 1
            correct += int(is_correct)
            outcome = 1.0 if is_correct else 0.5 if winner == "tie" else 0.0
            brier_sum += (float(rec["p_winner"]) - outcome) ** 2
            bp = by_period.setdefault(str(rec["period"]), {"n_decided": 0, "n_correct": 0})
            bp["n_decided"] += 1
            bp["n_correct"] += int(is_correct)
        rows.append(S.PredictionView(**rec, actual_winner=winner, actual_cats=cats, correct=is_correct))
    n_pred = sum(1 for r in rows if r.predicted_winner is not None)
    return S.PredictionsResponse(
        ids=svc.response_ids(state, snap, ctx.settings.default_seed),
        predictions=rows,
        summary=S.PredictionSummary(
            n_predicted=n_pred,
            n_decided=decided,
            n_correct=correct,
            hit_rate=(correct / decided) if decided else None,
            brier=(brier_sum / decided) if decided else None,
            by_period=by_period,
        ),
    )


# --- reads ---------------------------------------------------------------------------------------


def _odds_view(o) -> S.MatchupOddsView:
    return S.MatchupOddsView(
        period=o.period,
        manager_a=o.manager_a,
        manager_b=o.manager_b,
        expected_a=o.expected_a,
        expected_b=o.expected_b,
        p_win_a=o.p_win_a,
        p_tie=o.p_tie,
        p_win_b=o.p_win_b,
        cat_p_a=o.cat_p_a,
        modal_score=list(o.modal_score),
        games_a=o.games_a,
        games_b=o.games_b,
        notes=list(o.notes),
    )


def _pairs(
    ctx: AppContext, snap, state: DraftState, league: EspnLeague | None, period: int, seed: int
) -> list[S.MatchupPairView]:
    if league is None:
        return []
    t2m = _team_to_manager(state)
    status = status_overlay(snap, ctx.live_status(league.league_id))
    ir = _ir_ids(league, snap)
    out = []
    for m in league.matchups_for(period):
        home = t2m.get(m.home.team_id)
        away = t2m.get(m.away.team_id) if m.away is not None else None
        if home is None:
            continue
        odds = None
        if away is not None:
            odds = _odds_view(matchup_odds(snap, state, home, away, period, seed, ctx.get_schedule(), status, ir))
        out.append(S.MatchupPairView(period=period, home_manager_id=home, away_manager_id=away, odds=odds))
    return out


def _period(state: DraftState, rec: dict[str, Any] | None, requested: int | None) -> int:
    if requested is not None:
        return requested
    if rec and rec.get("current_period"):
        return int(rec["current_period"])
    return current_period(state.league.season, datetime.now(UTC).date())


def overview(ctx: AppContext, session_id: str, seed: int | None, period: int | None) -> S.SeasonOverview:
    meta, state = _session(ctx, session_id)
    snap = _snapshot(ctx, meta)
    seed = seed if seed is not None else ctx.settings.default_seed
    rec = ctx.store.get_sync(session_id)
    league_id = state.league.espn_league_id
    league = cached_league(ctx, league_id, state.league.season) if league_id else None
    power = _power(ctx, snap, state, league, seed)
    movement: dict[str, int] = {}
    prev = (rec or {}).get("previous_power") or None
    if prev:
        prev_rank = {r["manager_id"]: r["rank"] for r in prev}
        movement = {p.manager_id: prev_rank[p.manager_id] - p.rank for p in power if p.manager_id in prev_rank}
    period_n = _period(state, rec, period)
    pairs = _pairs(ctx, snap, state, league, period_n, seed)
    if pairs:
        record_predictions(ctx, session_id, state, pairs, period_n)
    uid = state.league.user_manager_id
    user_pair = next((p for p in pairs if uid in (p.home_manager_id, p.away_manager_id)), None)
    synced_at = (rec or {}).get("fetched_at")
    if league is not None and (synced_at is None or league.fetched_at > synced_at):
        synced_at = league.fetched_at
    return S.SeasonOverview(
        ids=svc.response_ids(state, snap, seed),
        linked=league_id is not None,
        league_name=league.settings.name if league else None,
        synced_at=synced_at,
        summary=(rec or {}).get("summary"),
        warnings=list((rec or {}).get("warnings") or []),
        current_period=period_n,
        league_categories=state.league.categories,
        manager_names={m.id: m.name for m in state.league.managers},
        power=[S.TeamPowerView(**p.__dict__) for p in power],
        movement=movement,
        matchups=pairs,
        user_matchup=user_pair,
    )


def matchup(
    ctx: AppContext, session_id: str, period: int, team_a: str, team_b: str, seed: int | None
) -> S.MatchupResponse:
    meta, state = _session(ctx, session_id)
    ids = {m.id for m in state.league.managers}
    if team_a not in ids or team_b not in ids or team_a == team_b:
        raise SeasonError(422, "unknown_manager", "team_a and team_b must be two different manager ids")
    snap = _snapshot(ctx, meta)
    seed = seed if seed is not None else ctx.settings.default_seed
    league_id = state.league.espn_league_id
    league = cached_league(ctx, league_id, state.league.season) if league_id else None
    status = status_overlay(snap, ctx.live_status(league_id) if league_id else None)
    odds = matchup_odds(snap, state, team_a, team_b, period, seed, ctx.get_schedule(), status, _ir_ids(league, snap))
    return S.MatchupResponse(ids=svc.response_ids(state, snap, seed), odds=_odds_view(odds))


def free_agents(
    ctx: AppContext, session_id: str, limit: int, position: str | None, q: str | None
) -> S.FreeAgentsResponse:
    meta, state = _session(ctx, session_id)
    snap = _snapshot(ctx, meta)
    rec = ctx.store.get_sync(session_id)
    league_id = state.league.espn_league_id
    league = cached_league(ctx, league_id, state.league.season) if league_id else None
    status = status_overlay(snap, ctx.live_status(league_id) if league_id else None)
    rows = rank_free_agents(snap, state, status, _ir_ids(league, snap), limit=limit, position=position, q=q)
    items = []
    for f in rows:
        drop = snap.index.get(f.best_drop) if f.best_drop else None
        items.append(
            S.FreeAgentView(
                player=svc.player_view(snap, snap.index[f.player_id], state),
                score=f.score,
                z=f.z,
                best_drop=svc.player_view(snap, drop, state) if drop is not None else None,
                drop_value=f.drop_value,
                swap_delta=f.swap_delta,
                injury_status=f.injury_status,
                percent_owned=f.percent_owned,
                flags=list(f.flags),
            )
        )
    return S.FreeAgentsResponse(
        ids=svc.response_ids(state, snap, ctx.settings.default_seed),
        items=items,
        synced_at=(rec or {}).get("fetched_at"),
    )


def results(ctx: AppContext, session_id: str, period: int, seed: int | None) -> S.WeekResultsResponse:
    meta, state = _session(ctx, session_id)
    league_id = state.league.espn_league_id
    if league_id is None:
        raise SeasonError(409, "not_linked", "link this session to an ESPN league first")
    league = cached_league(ctx, league_id, state.league.season)
    if league is None:
        raise SeasonError(409, "not_synced", "run an ESPN sync first")
    snap = _snapshot(ctx, meta)
    seed = seed if seed is not None else ctx.settings.default_seed
    rows = week_results(league, period, _team_to_manager(state), state.league.categories)

    def side(s):
        return (
            None
            if s is None
            else S.WeekSideView(manager_id=s.manager_id, values=s.values, results=s.results, cats_won=s.cats_won)
        )

    return S.WeekResultsResponse(
        ids=svc.response_ids(state, snap, seed),
        period=period,
        results=[
            S.WeekResultView(period=r.period, home=side(r.home), away=side(r.away), winner=r.winner) for r in rows
        ],
        projected=_pairs(ctx, snap, state, league, period, seed),
    )
