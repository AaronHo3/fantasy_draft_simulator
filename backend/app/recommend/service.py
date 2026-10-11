"""Turns engine results into API views with computed, unit-labeled explanations."""

from __future__ import annotations

import time
from dataclasses import replace

import numpy as np

from app.api import schemas as S
from app.draft.events import DraftState
from app.engine.categories import PRIM_IDX, PRIMITIVES, category_values, totals
from app.engine.layer_a import Candidate, LayerAResult, RankingContext, rank_layer_a, standardized
from app.engine.lineup import evaluate_roster, roster_slots
from app.league.config import CategoryKind, LeagueConfig
from app.league.strategy import Strategy
from app.projections.snapshot import Snapshot

PROJECTION_VERSION = "proj-v1"


def response_ids(state: DraftState, snap: Snapshot, seed: int) -> S.ResponseIds:
    return S.ResponseIds(
        draft_revision=state.draft_revision,
        strategy_revision=state.strategy_revision,
        league_revision=state.league_revision,
        last_seq=state.last_seq,
        snapshot_id=snap.snapshot_id,
        projection_version=PROJECTION_VERSION,
        seed=seed,
    )


def per_game_dict(snap: Snapshot, i: int) -> dict[str, float]:
    return {k: round(float(snap.per_game[i, PRIM_IDX[k]]), 3) for k in PRIMITIVES}


def player_view(snap: Snapshot, i: int, state: DraftState | None = None) -> S.PlayerView:
    p = snap.players[i]
    drafted_by, overall = None, None
    if state is not None:
        for rec in state.picks.values():
            if rec.player_id == p.player_id:
                drafted_by, overall = rec.manager_id, rec.overall
                break
    adp, rank = float(snap.adp[i]), float(snap.rank[i])
    return S.PlayerView(
        player_id=p.player_id,
        name=p.name,
        team=p.team,
        primary_position=p.primary_position,
        eligible_positions=sorted(p.eligible_positions),
        eligibility_source=p.eligibility_source,
        eligibility_verified=p.eligibility_verified,
        injury_status=p.injury_status,
        age=p.age,
        is_rookie=p.is_rookie,
        adp=None if np.isnan(adp) else round(adp, 1),
        rank=None if np.isnan(rank) else rank,
        projection_source=snap.projection_source[i],
        per_game=per_game_dict(snap, i),
        per_game_sd={k: round(float(snap.per_game_sd[i, PRIM_IDX[k]]), 3) for k in PRIMITIVES},
        drafted_by=drafted_by,
        drafted_overall=overall,
    )


def user_context(state: DraftState, snap: Snapshot, extra_roster: tuple[str, ...] = ()) -> RankingContext:
    uid = state.league.user_manager_id
    roster = tuple(r.player_id for r in state.roster(uid)) + extra_roster
    drafted = state.drafted_player_ids | frozenset(extra_roster)
    remaining = state.remaining_picks_for(uid) - len(extra_roster)
    cp = state.current_pick
    total_remaining = sum(1 for p in state.schedule if p.overall not in state.picks) - len(extra_roster)
    nxt, following = state.user_next_pick(), state.user_following_pick()
    horizon = None
    if cp is not None and following is not None:
        horizon = following.overall - cp.overall - 1  # picks by others before the user's following turn
    elif cp is not None and nxt is not None:
        horizon = nxt.overall - cp.overall
    return RankingContext(
        snap,
        state.league,
        state.strategy,
        drafted,
        roster,
        max(remaining, 0),
        state.picks_until_user_turn() if cp else None,
        total_remaining,
        horizon,
    )


def _team_totals(snap: Snapshot, idxs: list[int]) -> np.ndarray:
    if not idxs:
        return np.zeros(len(PRIMITIVES))
    return totals(snap.totals()[idxs])


def category_deltas(
    snap: Snapshot, league: LeagueConfig, roster_idx: list[int], cand_idx: int
) -> dict[str, S.CategoryDelta]:
    before = category_values(_team_totals(snap, roster_idx), league.categories)
    after = category_values(_team_totals(snap, [*roster_idx, cand_idx]), league.categories)
    out = {}
    for c in league.categories:
        b, a = before[c.key], after[c.key]
        unit = "rate" if c.kind == CategoryKind.ratio else "season total"
        d = None if (a is None or b is None) else a - b
        if c.kind == CategoryKind.ratio and b is None and a is not None:
            d = None
        out[c.key] = S.CategoryDelta(before=b, after=a, delta=d, unit=unit)
    return out


def reasons_for(
    snap: Snapshot,
    league: LeagueConfig,
    strategy: Strategy,
    cand: Candidate,
    keys: tuple[str, ...],
    open_slots: tuple[str, ...],
    res: LayerAResult | None = None,
) -> list[str]:
    i = cand.idx
    pg = snap.per_game[i]
    labels = {c.key: c.label for c in league.categories}
    contrib = cand.contributions
    order = np.argsort(-contrib)
    out: list[str] = []
    pos = [j for j in order if contrib[j] > 0.15][:3]
    if res is not None and len(res.marginal) and strategy.roster_aware:
        near = [keys[j] for j in order if contrib[j] > 0.15 and res.marginal[j] >= 0.75 and abs(res.roster_z[j]) < 0.9 * strategy.roster_scale][:2]
        capped = [keys[j] for j in range(len(keys)) if res.marginal[j] < 0.5 and cand.z[j] > 0.8]
        if near:
            out.append("Lifts " + " and ".join(labels[k].lower() for k in near) + ", where your roster is near the line.")
        if capped:
            out.append("Their " + " and ".join(labels[k].lower() for k in capped) + " add little: you already lead there.")
    if pos:
        bits = []
        for j in pos:
            k = keys[j]
            if k == "FG_PCT":
                bits.append(
                    f"FG% at {pg[PRIM_IDX['FGA']]:.1f} FGA/g ({pg[PRIM_IDX['FGM']] / max(pg[PRIM_IDX['FGA']], 1e-9):.3f})"
                )
            elif k == "FT_PCT":
                bits.append(
                    f"FT% at {pg[PRIM_IDX['FTA']]:.1f} FTA/g ({pg[PRIM_IDX['FTM']] / max(pg[PRIM_IDX['FTA']], 1e-9):.3f})"
                )
            else:
                bits.append(f"{labels[k].lower()} ({pg[PRIM_IDX[k]]:.1f}/g, z {cand.z[j]:+.1f})")
        out.append("Adds projected " + ", ".join(bits) + ".")
    if cand.slot and cand.fills_open_starting_slot:
        out.append(f"Fills your open {cand.slot} slot.")
    elif cand.slot == "BENCH":
        out.append("Would sit on the bench now (all starting slots covered or incompatible).")
    neg = [j for j in np.argsort(contrib) if cand.z[j] < -0.6][:2]
    if neg:
        parts = []
        for j in neg:
            k = keys[j]
            tag = strategy.punts.get(k)
            suffix = " (punted)" if tag else ""
            parts.append(f"{labels[k]}{suffix}")
        out.append("Costs " + " and ".join(parts) + ".")
    if cand.replacement_player_id:
        rn = snap.players[snap.index[cand.replacement_player_id]].name
        out.append(f"Value above the likely-available alternative {rn}: {cand.score - cand.risk_adjustment:+.2f}.")
    gp = pg[PRIM_IDX["GP"]]
    out.append(f"Projected {gp:.0f} games at {pg[PRIM_IDX['MIN']]:.1f} min; {cand.survival_hint}.")
    return out


def candidate_view(
    snap: Snapshot,
    league: LeagueConfig,
    strategy: Strategy,
    res: LayerAResult,
    cand: Candidate,
    roster_idx: list[int],
    with_deltas: bool,
) -> S.CandidateView:
    i = cand.idx
    p = snap.players[i]
    keys = res.keys
    adp, rank = float(snap.adp[i]), float(snap.rank[i])
    repl_name = None
    if cand.replacement_player_id:
        repl_name = snap.players[snap.index[cand.replacement_player_id]].name
    return S.CandidateView(
        player_id=p.player_id,
        name=p.name,
        team=p.team,
        primary_position=p.primary_position,
        eligible_positions=sorted(p.eligible_positions),
        eligibility_verified=p.eligibility_verified,
        injury_status=p.injury_status,
        score=round(cand.score, 4),
        tier=cand.tier,
        base_value=round(cand.base_value, 4),
        replacement_value=round(cand.replacement_value, 4),
        replacement_player_id=cand.replacement_player_id,
        replacement_name=repl_name,
        slot=cand.slot,
        fills_open_starting_slot=cand.fills_open_starting_slot,
        completion_ok=cand.completion_ok,
        risk_adjustment=round(cand.risk_adjustment, 4),
        value_sd=round(cand.value_sd, 4),
        survival_hint=cand.survival_hint,
        adp=None if np.isnan(adp) else round(adp, 1),
        rank=None if np.isnan(rank) else rank,
        flags=list(cand.flags),
        z={k: round(float(cand.z[j]), 3) for j, k in enumerate(keys)},
        contributions={k: round(float(cand.contributions[j]), 3) for j, k in enumerate(keys)},
        reasons=reasons_for(snap, league, strategy, cand, keys, res.user_open_slots, res),
        per_game=per_game_dict(snap, i),
        games=float(snap.games[i]),
        minutes=float(snap.per_game[i, PRIM_IDX["MIN"]]),
        projection_source=snap.projection_source[i],
        category_deltas=category_deltas(snap, league, roster_idx, i) if with_deltas else None,
    )


def roster_view(snap: Snapshot, state: DraftState, extra: tuple[str, ...] = ()) -> S.RosterView:
    league = state.league
    uid = league.user_manager_id
    ids = [r.player_id for r in state.roster(uid)] + list(extra)
    idxs = [snap.index[p] for p in ids if p in snap.index]
    positions = [snap.players[i].eligible_positions for i in idxs]
    primaries = [snap.players[i].primary_position for i in idxs]
    unverified = [not snap.players[i].eligibility_verified for i in idxs]
    remaining = state.remaining_picks_for(uid) - len(extra)
    drafted = state.drafted_player_ids | frozenset(extra)
    avail_pos = [p.eligible_positions for p in snap.players if p.player_id not in drafted]
    rep = evaluate_roster(league, positions, primaries, max(remaining, 0), avail_pos, unverified)
    slots = roster_slots(league)
    by_slot: dict[int, int] = {j: i for i, j in rep.assignment.assigned.items()}
    assignments = []
    for j, s in enumerate(slots):
        i = by_slot.get(j)
        pid = ids[i] if i is not None else None
        assignments.append(
            S.RosterSlotView(slot=s, player_id=pid, name=snap.players[idxs[i]].name if i is not None else None)
        )
    return S.RosterView(
        assignments=assignments,
        unassigned=[ids[i] for i in rep.assignment.unassigned_players],
        open_starting_slots=list(rep.open_starting_slots),
        bench_used=rep.bench_used,
        legal=rep.legal,
        caps_ok=rep.caps_ok,
        cap_violations=dict(rep.caps.violations),
        completion_feasible=rep.completion_feasible,
        completion_detail=rep.completion_detail,
        coverage_ratio=round(rep.coverage_ratio, 3),
    )


def category_profile(snap: Snapshot, state: DraftState, res: LayerAResult, roster_idx: list[int]) -> S.CategoryProfile:
    league, strategy = state.league, state.strategy
    tot = _team_totals(snap, roster_idx)
    vals = category_values(tot, league.categories)
    st = standardized(snap, league)
    z = {k: round(float(st.z_totals[roster_idx, j].sum()), 3) if roster_idx else 0.0 for j, k in enumerate(res.keys)}
    return S.CategoryProfile(
        totals={k: (None if v is None else round(v, 4)) for k, v in vals.items()},
        attempts={
            "FGA": round(float(tot[PRIM_IDX["FGA"]]), 1),
            "FTA": round(float(tot[PRIM_IDX["FTA"]]), 1),
            "FG3A": round(float(tot[PRIM_IDX["FG3A"]]), 1),
        },
        z=z,
        punt_labels={k: (strategy.punts[k].value if k in strategy.punts else None) for k in res.keys},
        weights={k: float(res.weights[j]) for j, k in enumerate(res.keys)},
        standardization=res.standardization.to_dict(),
    )


def fast_recommendation(
    snap: Snapshot, state: DraftState, req: S.FastRecommendRequest, seed: int
) -> S.RecommendationResponse:
    t0 = time.perf_counter()
    extra: tuple[str, ...] = ()
    notes: list[str] = []
    if req.preview_player_id:
        if req.preview_player_id in state.drafted_player_ids:
            notes.append("Preview player is already drafted; showing the committed state.")
        elif req.preview_player_id in snap.index:
            extra = (req.preview_player_id,)
        else:
            notes.append("Preview player not found in this snapshot.")
    ctx = user_context(state, snap, extra)
    cp = state.current_pick
    res = rank_layer_a(ctx, cp.overall if cp else None)
    roster_idx = [snap.index[p] for p in ctx.user_roster_ids if p in snap.index]
    top = res.top(req.limit)
    views = [
        candidate_view(snap, state.league, state.strategy, res, c, roster_idx, j < req.include_deltas)
        for j, c in enumerate(top)
    ]
    if not state.league.format_confirmed:
        notes.append(
            f"Scoring format not confirmed: rankings assume {state.league.scoring_format.value}. Confirm it in setup."
        )
    if snap.is_demo:
        notes.append("DEMO DATA: synthetic players, not real projections.")
    notes.extend(res.notes)
    if views and len(views) > 1 and views[0].tier == views[1].tier:
        notes.append(
            f"Top candidates are within one tier (gap {views[0].score - views[1].score:.2f}); treat them as a group."
        )
    preview_view = None
    if extra:
        base_ctx = user_context(state, snap)
        base_res = rank_layer_a(base_ctx, cp.overall if cp else None)
        base_roster = [snap.index[p] for p in base_ctx.user_roster_ids if p in snap.index]
        cand = next((c for c in base_res.candidates if c.player_id == extra[0]), None)
        if cand is not None:
            preview_view = candidate_view(snap, state.league, state.strategy, base_res, cand, base_roster, True)
    return S.RecommendationResponse(
        ids=response_ids(state, snap, seed),
        tier="A",
        computed_ms=round((time.perf_counter() - t0) * 1000, 1),
        highlighted=views[0] if views else None,
        shortlist=views,
        user_roster=roster_view(snap, state, extra),
        category_profile=category_profile(snap, state, res, roster_idx),
        notes=notes,
        preview_player_id=req.preview_player_id if extra else None,
        preview_candidate=preview_view,
    )


def compare_players(snap: Snapshot, state: DraftState, player_ids: list[str], seed: int) -> S.CompareResponse:
    ctx = user_context(state, snap)
    cp = state.current_pick
    res = rank_layer_a(ctx, cp.overall if cp else None)
    by_id = {c.player_id: c for c in res.candidates}
    roster_idx = [snap.index[p] for p in ctx.user_roster_ids if p in snap.index]
    views = []
    for pid in player_ids:
        c = by_id.get(pid)
        if c is None:
            if pid not in snap.index:
                raise KeyError(pid)
            # drafted player: build a neutral candidate for display
            i = snap.index[pid]
            st = standardized(snap, state.league)
            w = res.weights
            c = Candidate(
                i,
                pid,
                float("nan"),
                float(st.z_totals[i] @ w),
                0.0,
                None,
                None,
                False,
                True,
                0.0,
                0.0,
                st.z_totals[i],
                st.z_totals[i] * w,
                ("already drafted",),
                "n/a",
            )
            c = replace(c, score=0.0)
        views.append(candidate_view(snap, state.league, state.strategy, res, c, roster_idx, True))
    return S.CompareResponse(ids=response_ids(state, snap, seed), players=views, keys=list(res.keys))


def state_view(state: DraftState) -> S.DraftStateView:
    def pv(p):
        return (
            None
            if p is None
            else S.PickView(
                overall=p.overall,
                round=p.round,
                pick_in_round=p.pick_in_round,
                manager_id=p.manager_id,
                original_manager_id=p.original_manager_id,
                keeper_player_id=p.keeper_player_id,
            )
        )

    return S.DraftStateView(
        draft_revision=state.draft_revision,
        strategy_revision=state.strategy_revision,
        league_revision=state.league_revision,
        last_seq=state.last_seq,
        is_complete=state.is_complete,
        format_confirmed=state.league.format_confirmed,
        current_pick=pv(state.current_pick),
        on_clock_manager_id=state.on_clock_manager_id,
        user_next_pick=pv(state.user_next_pick()),
        user_following_pick=pv(state.user_following_pick()),
        picks_until_user_turn=state.picks_until_user_turn(),
        picks=[S.PickRecordView(**r.to_dict()) for r in sorted(state.picks.values(), key=lambda r: r.overall)],
        schedule=[pv(p) for p in state.schedule],
        rosters={m: [r.player_id for r in rs] for m, rs in state.rosters().items()},
        drafted_player_ids=sorted(state.drafted_player_ids),
        remaining_user_picks=state.remaining_picks_for(state.league.user_manager_id),
        warnings=list(state.warnings),
        strategy=state.strategy,
        league=state.league,
    )


def league_profiles(snap: Snapshot, state: DraftState, seed: int) -> S.LeagueProfilesResponse:
    """Every manager's projected category totals, z-sums and per-category league rank."""
    league = state.league
    keys = [c.key for c in league.categories]
    st = standardized(snap, league)
    rows: list[dict] = []
    for m in league.managers:
        idxs = [snap.index[r.player_id] for r in state.roster(m.id) if r.player_id in snap.index]
        tot = _team_totals(snap, idxs)
        vals = category_values(tot, league.categories)
        z = {k: float(st.z_totals[idxs, j].sum()) if idxs else 0.0 for j, k in enumerate(keys)}
        rows.append({"manager_id": m.id, "name": m.name, "is_user": m.id == league.user_manager_id,
                     "n_players": len(idxs), "totals": vals, "z": z,
                     "attempts": {"FGA": float(tot[PRIM_IDX["FGA"]]), "FTA": float(tot[PRIM_IDX["FTA"]])}})
    ranks: dict[str, dict[str, int | None]] = {r["manager_id"]: {} for r in rows}
    for c in league.categories:
        scored = [(r["manager_id"], r["totals"][c.key]) for r in rows]
        known = [(mid, v) for mid, v in scored if v is not None]
        known.sort(key=lambda t: t[1], reverse=c.higher_is_better)
        for pos, (mid, _) in enumerate(known, start=1):
            ranks[mid][c.key] = pos
        for mid, v in scored:
            if v is None:
                ranks[mid][c.key] = None
    out = []
    for r in rows:
        rk = ranks[r["manager_id"]]
        out.append(S.ManagerProfile(
            manager_id=r["manager_id"], name=r["name"], is_user=r["is_user"], n_players=r["n_players"],
            totals={k: (None if v is None else round(v, 4)) for k, v in r["totals"].items()},
            attempts={k: round(v, 1) for k, v in r["attempts"].items()},
            z={k: round(v, 3) for k, v in r["z"].items()}, rank=rk,
            categories_top3=sum(1 for v in rk.values() if v is not None and v <= 3)))
    return S.LeagueProfilesResponse(ids=response_ids(state, snap, seed), keys=keys, managers=out)
