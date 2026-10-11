"""Layers B/C: roster-aware, format-correct refinement of the Layer A shortlist under a time budget.

For each shortlist candidate c and each draft rollout r (common random numbers across candidates):
  utility_now(c)   = objective of the user's completed roster when c is taken at the user's next pick
  utility_alt      = objective when the continuation policy picks instead (the best alternative)
  marginal(c)      = mean_r [utility_now(c) - utility_alt]
  survival(c)      = share of policy rollouts in which c is still available at the user's next pick
  wait_value(c)    = objective when the alternative is taken now and c is targeted at the following pick
Objectives come from simulated weekly matchups against every opponent's completed roster under the
league's actual scoring format (each / most / roto). Rollouts stop when the wall-clock budget is hit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.api import schemas as S
from app.draft.events import DraftState
from app.engine.layer_a import rank_layer_a, standardized
from app.engine.opponents import DemandModel, Rollout, build_demand, rollout_draft
from app.engine.schedule_model import games_per_week_for_players
from app.engine.simulation import (
    SimConfig,
    category_outcomes,
    category_win_probabilities,
    objective,
    roto_objective,
    simulate_players_week,
    team_totals,
)
from app.league.config import LeagueConfig, LineupMode, ScoringFormat
from app.projections.snapshot import Snapshot
from app.recommend.service import response_ids, user_context

OBJECTIVE_LABELS = {
    ScoringFormat.h2h_each_category: "expected categories won per weekly matchup (of %d)",
    ScoringFormat.h2h_most_categories: "probability of winning a weekly matchup",
    ScoringFormat.roto: "expected rotisserie points (of %d)",
}
MIN_ROLLOUTS = 2
MAX_ROLLOUTS = 200


@dataclass
class _Eval:
    util_now: list[float]
    util_alt: list[float]
    survived: list[bool]
    wait: list[float]
    cat_probs: list[np.ndarray]


def _daily_weights(snap: Snapshot, league: LeagueConfig, roster: list[int]) -> np.ndarray | None:
    """Daily-lineup collision factor: expected counted share per player (approximation, see schedule_model)."""
    if league.lineup_mode != LineupMode.daily or not snap.team_games_per_week:
        return None
    n_start = len(league.starting_slots)
    gpw = np.array([snap.team_games_per_week.get(snap.players[i].team or "", 3.5) for i in roster])
    # expected players with a game on a given day ≈ sum(gpw)/7; share counted when that exceeds the slots
    k = gpw.sum() / 7.0
    share = min(1.0, n_start / k) if k > 0 else 1.0
    return np.full(len(roster), share)


def _matchup_utility(
    snap: Snapshot, league: LeagueConfig, rollout: Rollout, week_sims: np.ndarray, sim_idx: dict[int, int], uid: str
) -> tuple[float, np.ndarray]:
    """Mean objective of the user's roster vs every opponent, plus per-category win probabilities."""
    cats, fmt, tie = league.categories, league.scoring_format, league.tie_rule
    n_start = len(league.starting_slots)

    def tt(manager: str) -> np.ndarray:
        roster = rollout.rosters[manager]
        idx = [sim_idx[i] for i in roster]
        w = _daily_weights(snap, league, roster)
        if w is not None:
            return team_totals(week_sims, idx, weights=w)
        return team_totals(week_sims, idx, max_starters=n_start)

    mine = tt(uid)
    if fmt == ScoringFormat.roto:
        teams = [m.id for m in league.managers]
        stack = np.stack([mine if m == uid else tt(m) for m in teams], axis=1)  # [S, T, P]
        pts = roto_objective(stack, cats)
        probs = np.zeros(len(cats))
        return float(pts[teams.index(uid)]), probs
    utils, probs = [], []
    for m in league.managers:
        if m.id == uid:
            continue
        out = category_outcomes(mine, tt(m.id), cats, tie)
        utils.append(objective(out, fmt, tie).mean())
        probs.append(category_win_probabilities(out))
    return float(np.mean(utils)), np.mean(probs, axis=0)


def run_refinement(snap: Snapshot, state: DraftState, req: S.RefineRequest, seed: int) -> S.RefinementResponse:  # noqa: C901
    t0 = time.perf_counter()
    league, strategy = state.league, state.strategy
    budget_ms = req.budget_ms or strategy.sim_budget_ms
    n_week = max(40, min(req.scenarios or strategy.sim_scenarios, 2000) // 4)
    ids = response_ids(state, snap, seed)
    uid = league.user_manager_id
    nxt = state.user_next_pick()
    fmt = league.scoring_format
    label = (
        OBJECTIVE_LABELS[fmt]
        % (len(league.categories) if fmt != ScoringFormat.roto else len(league.categories) * league.n_managers)
        if "%d" in OBJECTIVE_LABELS[fmt]
        else OBJECTIVE_LABELS[fmt]
    )
    notes: list[str] = []
    if nxt is None:
        return S.RefinementResponse(
            ids=ids,
            tier="B",
            computed_ms=0.0,
            budget_ms=budget_ms,
            scenarios=0,
            seed=seed,
            objective_label=label,
            opponent_model="n/a",
            highlighted_player_id=None,
            candidates=[],
            notes=["The user has no remaining picks."],
        )
    ctx = user_context(state, snap)
    cp = state.current_pick
    layer_a = rank_layer_a(ctx, cp.overall if cp else None)
    shortlist = [c for c in layer_a.candidates if c.completion_ok][: req.limit]
    if not shortlist:
        shortlist = list(layer_a.candidates[: req.limit])
    st = standardized(snap, league)
    base_value = st.z_totals @ np.asarray(strategy.weight_vector([c.key for c in league.categories]))
    demand: DemandModel = build_demand(snap, st.z_totals.sum(axis=1))
    if demand.is_proxy:
        notes.append("No ADP in this snapshot: opponents modeled from value order (proxy); survival is qualitative.")
    current_picks = {o: r.player_id for o, r in state.picks.items()}
    drafted = state.drafted_player_ids
    on_clock = cp is not None and cp.manager_id == uid
    following = state.user_following_pick()
    rng = np.random.default_rng(seed)
    u_all = rng.random((MAX_ROLLOUTS, len(state.schedule)))
    evals = {c.player_id: _Eval([], [], [], [], []) for c in shortlist}
    cand_idx = {c.player_id: c.idx for c in shortlist}
    sim_cfg = SimConfig(n_scenarios=n_week)
    gpw = games_per_week_for_players([p.team for p in snap.players], snap.team_games_per_week)
    notes.append(f"Games per week: {snap.schedule_label}.")
    if league.lineup_mode == LineupMode.daily:
        notes.append("Daily lineups: counted starts use an expected-collision approximation, not per-day optimization.")
    rollouts_done = 0
    did_wait = False
    for r in range(MAX_ROLLOUTS):
        if rollouts_done >= MIN_ROLLOUTS and (time.perf_counter() - t0) * 1000 > budget_ms * 0.85:
            break
        u_row = u_all[r]
        alt = rollout_draft(snap, league, state.schedule, current_picks, drafted, base_value, demand, u_row)
        # one weekly simulation per rollout for every player that could appear in any roster
        all_idx = sorted({i for roster in alt.rosters.values() for i in roster} | set(cand_idx.values()))
        week_rng = np.random.default_rng(seed * 1000 + r)
        sims_all = simulate_players_week(week_rng, snap.per_game, snap.games, sim_cfg, gpw)  # common random numbers
        sim_idx = {i: i for i in range(snap.n)}
        del all_idx
        util_alt, _ = _matchup_utility(snap, league, alt, sims_all, sim_idx, uid)
        taken_before_next = {i for o, i in alt.picks.items() if o < nxt.overall}
        for c in shortlist:
            ev = evals[c.player_id]
            survived = on_clock or (c.idx not in taken_before_next)
            ev.survived.append(bool(survived))
            if not survived:
                continue
            roll_c = rollout_draft(
                snap,
                league,
                state.schedule,
                current_picks,
                drafted,
                base_value,
                demand,
                u_row,
                forced={nxt.overall: c.idx},
            )
            util_c, probs = _matchup_utility(snap, league, roll_c, sims_all, sim_idx, uid)
            ev.util_now.append(util_c)
            ev.util_alt.append(util_alt)
            ev.cat_probs.append(probs)
        rollouts_done += 1
    # draft-now vs wait for the top candidates if there is time and a following pick
    ranked = sorted(shortlist, key=lambda c: -_mean(evals[c.player_id].util_now, evals[c.player_id].util_alt))
    if following is not None and (time.perf_counter() - t0) * 1000 < budget_ms * 0.85:
        for c in ranked[:4]:
            if (time.perf_counter() - t0) * 1000 > budget_ms * 0.95:
                break
            ev = evals[c.player_id]
            for r in range(min(rollouts_done, 6)):
                u_row = u_all[r]
                roll_w = rollout_draft(
                    snap,
                    league,
                    state.schedule,
                    current_picks,
                    drafted,
                    base_value,
                    demand,
                    u_row,
                    user_targets=[c.idx],
                )
                if roll_w.picks.get(nxt.overall) == c.idx:
                    # the policy itself took c at the next pick (c was the best alternative): wait == now
                    continue
                week_rng = np.random.default_rng(seed * 1000 + r)
                sims_all = simulate_players_week(week_rng, snap.per_game, snap.games, sim_cfg, gpw)
                util_w, _ = _matchup_utility(snap, league, roll_w, sims_all, {i: i for i in range(snap.n)}, uid)
                ev.wait.append(util_w)
                did_wait = True
    cands: list[S.RefinedCandidate] = []
    keys = [c.key for c in league.categories]
    for c in shortlist:
        ev = evals[c.player_id]
        if ev.util_now:
            diffs = np.array(ev.util_now) - np.array(ev.util_alt)
            marginal = float(diffs.mean())
            unc = float(diffs.std(ddof=1) / np.sqrt(len(diffs))) if len(diffs) > 1 else float("nan")
            util_now, util_alt = float(np.mean(ev.util_now)), float(np.mean(ev.util_alt))
            probs = np.mean(ev.cat_probs, axis=0)
        else:
            marginal, unc, util_now, util_alt, probs = (
                float("nan"),
                float("nan"),
                float("nan"),
                float("nan"),
                np.zeros(len(keys)),
            )
        surv = float(np.mean(ev.survived)) if ev.survived else None
        wait_v = float(np.mean(ev.wait)) if ev.wait else None
        adv = (util_now - wait_v) if (wait_v is not None and ev.util_now) else None
        expl = []
        p = snap.players[c.idx]
        if ev.util_now:
            expl.append(
                f"Marginal value vs the policy's alternative: {marginal:+.3f} ({label}), ± {unc:.3f} MC error over {len(diffs)} rollouts."
            )
        else:
            expl.append("Gone before your next pick in every rollout; no conditional utility estimate.")
        if surv is not None and not on_clock:
            expl.append(
                f"Still available at your next pick in {surv:.0%} of rollouts ({'ADP-based' if not demand.is_proxy else 'value-proxy'} opponent model)."
            )
        if adv is not None:
            expl.append(
                f"Drafting now vs waiting one turn: {adv:+.3f} (waiting assumes the alternative now, this player later if available)."
            )
        if ev.cat_probs and fmt != ScoringFormat.roto:
            top = np.argsort(-probs)[:3]
            expl.append(
                "Strongest categories after this pick: " + ", ".join(f"{keys[j]} {probs[j]:.0%}" for j in top) + "."
            )
        cands.append(
            S.RefinedCandidate(
                player_id=p.player_id,
                name=p.name,
                layer_a_score=round(c.score, 4),
                utility_now=_r(util_now),
                utility_alternative=_r(util_alt),
                marginal_utility=_r(marginal),
                survival_probability=None if on_clock else surv,
                survival_label=(
                    "n/a: you are on the clock" if on_clock else ("proxy" if demand.is_proxy else "model estimate")
                ),
                wait_value=None if wait_v is None else round(wait_v, 4),
                draft_now_advantage=None if adv is None else round(adv, 4),
                objective_estimate=_r(util_now),
                objective_label=label,
                category_win_probs={k: round(float(probs[j]), 3) for j, k in enumerate(keys)},
                uncertainty=_r(unc),
                tier=1,
                explanation=expl,
            )
        )
    cands.sort(
        key=lambda x: (np.isnan(x.marginal_utility), -x.marginal_utility if not np.isnan(x.marginal_utility) else 0)
    )
    # tiers by MC uncertainty
    tier = 1
    for i in range(1, len(cands)):
        prev, cur = cands[i - 1], cands[i]
        gap = (
            prev.marginal_utility - cur.marginal_utility
            if not (np.isnan(prev.marginal_utility) or np.isnan(cur.marginal_utility))
            else 0.0
        )
        noise = np.nanmax([prev.uncertainty, cur.uncertainty, 1e-9]) if not np.isnan(cur.uncertainty) else 0.0
        if gap > 1.5 * noise:
            tier += 1
        cands[i] = cur.model_copy(update={"tier": tier})
    if rollouts_done < 4:
        notes.append(
            f"Only {rollouts_done} draft rollouts fit the {budget_ms} ms budget; estimates are coarse (Layer B)."
        )
    if not did_wait and following is not None:
        notes.append("Draft-now vs wait analysis skipped (budget).")
    notes.append("Simulated results describe the simulator's assumptions (MODEL_CARD.md), not guaranteed outcomes.")
    return S.RefinementResponse(
        ids=ids,
        tier="C" if rollouts_done >= 4 else "B",
        computed_ms=round((time.perf_counter() - t0) * 1000, 1),
        budget_ms=budget_ms,
        scenarios=rollouts_done * n_week,
        seed=seed,
        objective_label=label,
        opponent_model=demand.label,
        highlighted_player_id=cands[0].player_id if cands else None,
        candidates=cands,
        notes=notes,
    )


def _mean(a: list[float], b: list[float]) -> float:
    if not a:
        return -1e9
    return float(np.mean(np.array(a) - np.array(b)))


def _r(x: float) -> float:
    return float(round(x, 4)) if np.isfinite(x) else float("nan")
