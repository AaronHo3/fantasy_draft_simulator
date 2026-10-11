"""Punt advisor: compare strategy scenarios for the user's current roster under the league's real scoring.

For each scenario (balanced, each single fixed punt, and the two best pairs) the user's remaining picks
are completed with the fast-layer continuation policy under that scenario's weights, opponents draft by
demand, and every completed league is scored with the weekly matchup simulation under the actual
category rules (punted categories still count). Rollouts share random numbers across scenarios, so
differences reflect the strategy, not luck. Nothing is applied automatically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.api import schemas as S
from app.draft.events import DraftState
from app.engine.layer_a import standardized
from app.engine.opponents import build_demand, rollout_draft
from app.engine.schedule_model import games_per_week_for_players
from app.engine.simulation import SimConfig, simulate_players_week
from app.league.config import ScoringFormat
from app.league.strategy import PuntKind, Strategy
from app.projections.snapshot import Snapshot
from app.recommend.refine import _matchup_utility
from app.recommend.service import response_ids


@dataclass
class _Scenario:
    key: str
    label: str
    punts: dict[str, PuntKind]


def _scenarios(keys: list[str], current: Strategy) -> list[_Scenario]:
    out = [_Scenario("balanced", "Balanced (no punts)", {})]
    out += [_Scenario(f"punt_{k}", f"Punt {k}", {k: PuntKind.fixed}) for k in keys]
    cur = {k: v for k, v in current.punts.items() if v == PuntKind.fixed}
    if cur and all(s.punts != cur for s in out):
        out.insert(1, _Scenario("current", "Current strategy", dict(cur)))
    return out


def analyze_punts(snap: Snapshot, state: DraftState, budget_ms: int, seed: int, n_rollouts: int = 6,
                  n_week: int = 150) -> S.PuntAdvisorResponse:  # noqa: C901
    t0 = time.perf_counter()
    league, strategy = state.league, state.strategy
    keys = [c.key for c in league.categories]
    uid = league.user_manager_id
    ids = response_ids(state, snap, seed)
    fmt = league.scoring_format
    label = {ScoringFormat.h2h_each_category: f"expected categories won per weekly matchup (of {len(keys)})",
             ScoringFormat.h2h_most_categories: "probability of winning a weekly matchup",
             ScoringFormat.roto: "expected rotisserie points"}[fmt]
    if state.is_complete or state.user_next_pick() is None:
        return S.PuntAdvisorResponse(ids=ids, objective_label=label, computed_ms=0.0, rollouts=0, scenarios=[],
                                     notes=["The draft is complete; punts no longer change the outcome."])
    st = standardized(snap, league)
    demand = build_demand(snap, st.z_totals.sum(axis=1))
    current_picks = {o: r.player_id for o, r in state.picks.items()}
    drafted = state.drafted_player_ids
    rng = np.random.default_rng(seed)
    u_all = rng.random((n_rollouts, len(state.schedule)))
    gpw = games_per_week_for_players([p.team for p in snap.players], snap.team_games_per_week)
    sim_cfg = SimConfig(n_scenarios=n_week)
    sims = [simulate_players_week(np.random.default_rng(seed * 1000 + r), snap.per_game, snap.games, sim_cfg, gpw) for r in range(n_rollouts)]
    sim_idx = {i: i for i in range(snap.n)}
    results = []
    singles = _scenarios(keys, strategy)
    # evaluate singles first, then the two best pairs if budget allows
    def evaluate(sc: _Scenario) -> dict:
        strat = strategy.model_copy(update={"punts": sc.punts, "mode": "custom" if sc.punts else "balanced"})
        w = np.asarray(strat.weight_vector(keys))
        base_value = st.z_totals @ w
        utils, probs, targets = [], [], {}
        for r in range(n_rollouts):
            roll = rollout_draft(snap, league, state.schedule, current_picks, drafted, base_value, demand, u_all[r])
            u, p = _matchup_utility(snap, league, roll, sims[r], sim_idx, uid)
            utils.append(u)
            probs.append(p)
            for o, i in roll.picks.items():
                if state.schedule[o - 1].manager_id == uid:
                    targets[i] = targets.get(i, 0) + 1
                    break
        top = sorted(targets.items(), key=lambda kv: -kv[1])[:3]
        return {"sc": sc, "mean": float(np.mean(utils)), "se": float(np.std(utils, ddof=1) / np.sqrt(len(utils))) if len(utils) > 1 else 0.0,
                "probs": np.mean(probs, axis=0), "targets": [snap.players[i].name for i, _ in top]}

    for sc in singles:
        results.append(evaluate(sc))
        if (time.perf_counter() - t0) * 1000 > budget_ms * 0.8:
            break
    base = next((r for r in results if r["sc"].key == "balanced"), results[0])
    ranked_singles = sorted((r for r in results if r["sc"].key.startswith("punt_")), key=lambda r: -r["mean"])
    if len(ranked_singles) >= 2 and (time.perf_counter() - t0) * 1000 < budget_ms * 0.8:
        a, b = ranked_singles[0]["sc"], ranked_singles[1]["sc"]
        pair = _Scenario(f"punt_{list(a.punts)[0]}_{list(b.punts)[0]}", f"Punt {list(a.punts)[0]} + {list(b.punts)[0]}", {**a.punts, **b.punts})
        results.append(evaluate(pair))
    out = []
    for r in results:
        probs = r["probs"]
        strong = int(np.sum(probs >= 0.55))
        toss = int(np.sum((probs > 0.45) & (probs < 0.55)))
        out.append(S.PuntScenario(
            key=r["sc"].key, label=r["sc"].label, punts={k: v.value for k, v in r["sc"].punts.items()},
            objective=round(r["mean"], 3), se=round(r["se"], 3), delta_vs_balanced=round(r["mean"] - base["mean"], 3),
            category_win_probs={k: round(float(probs[j]), 3) for j, k in enumerate(keys)},
            strong_categories=strong, tossup_categories=toss, likely_targets=r["targets"],
            is_current=(r["sc"].punts == {k: v for k, v in strategy.punts.items() if v == PuntKind.fixed})))
    out.sort(key=lambda s: -s.objective)
    best = out[0]
    notes = [f"{n_rollouts} draft rollouts × {n_week} simulated weeks per scenario; punted categories still count in the score.",
             "A difference smaller than about two standard errors is noise; prefer the simpler strategy when scenarios tie."]
    if best.key != "balanced" and best.delta_vs_balanced > 2 * max(best.se, base["se"], 1e-9):
        notes.append(f"{best.label} projects {best.delta_vs_balanced:+.2f} {label.split(' (')[0]} over balanced for your current roster.")
    else:
        notes.append("No punt is clearly better than balanced for your current roster; keep it balanced for now and re-check after your next picks.")
    return S.PuntAdvisorResponse(ids=ids, objective_label=label, computed_ms=round((time.perf_counter() - t0) * 1000, 1),
                                 rollouts=n_rollouts, scenarios=out, notes=notes)
