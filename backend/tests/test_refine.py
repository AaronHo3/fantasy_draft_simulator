import math
import time

import numpy as np
import pytest

from app.api import schemas as S
from app.demo.generate import generate_demo_snapshot
from app.draft.events import Event, EventType, initial_state, now_iso, replay
from app.league.config import ScoringFormat, demo_league_config
from app.recommend.refine import run_refinement


@pytest.fixture(scope="module")
def snap():
    return generate_demo_snapshot()


def state_after(n_picks, snap, fmt=ScoringFormat.h2h_most_categories):
    league = demo_league_config().model_copy(update={"scoring_format": fmt})
    st = initial_state(league)
    order = np.argsort(np.where(np.isfinite(snap.adp), snap.adp, 1e9))
    events = []
    for k in range(n_picks):
        p = st.schedule[k]
        events.append(
            Event(
                k + 2,
                EventType.pick_committed,
                {"player_id": snap.players[order[k]].player_id, "overall": p.overall, "manager_id": p.manager_id},
                f"k{k}",
                now_iso(),
            )
        )
    return replay(league, events)


def test_refinement_on_clock_produces_marginals_and_respects_budget(snap):
    st = state_after(5, snap)  # user (m06) is on the clock at pick 6
    t = time.perf_counter()
    res = run_refinement(snap, st, S.RefineRequest(limit=5, budget_ms=1500, scenarios=200), seed=1)
    dt = (time.perf_counter() - t) * 1000
    assert dt < 3500, dt
    assert res.tier in ("B", "C") and len(res.candidates) == 5
    assert res.ids.draft_revision == st.draft_revision
    assert res.opponent_model == "adp:demo"
    assert all(c.survival_probability is None for c in res.candidates)  # on the clock
    assert all(math.isfinite(c.marginal_utility) for c in res.candidates)
    assert "probability of winning" in res.objective_label
    assert all(0.0 <= c.utility_now <= 1.0 for c in res.candidates)
    assert res.candidates[0].marginal_utility >= res.candidates[-1].marginal_utility
    assert all(
        set(c.category_win_probs) == {"PTS", "REB", "AST", "STL", "BLK", "FG3M", "FG_PCT", "FT_PCT", "TOV"}
        for c in res.candidates
    )


def test_refinement_between_turns_reports_survival(snap):
    st = state_after(7, snap)  # m08 on the clock; user's next pick is 19
    res = run_refinement(snap, st, S.RefineRequest(limit=4, budget_ms=1500, scenarios=120), seed=2)
    assert all(c.survival_probability is not None and 0 <= c.survival_probability <= 1 for c in res.candidates)
    assert all(c.survival_label == "model estimate" for c in res.candidates)


def test_each_category_objective_scale(snap):
    st = state_after(5, snap, ScoringFormat.h2h_each_category)
    res = run_refinement(snap, st, S.RefineRequest(limit=3, budget_ms=1200, scenarios=100), seed=3)
    assert "categories won" in res.objective_label
    assert all(0 <= c.utility_now <= 9 for c in res.candidates if math.isfinite(c.utility_now))


def test_roto_objective_runs(snap):
    st = state_after(5, snap, ScoringFormat.roto)
    res = run_refinement(snap, st, S.RefineRequest(limit=3, budget_ms=1200, scenarios=100), seed=4)
    assert "rotisserie" in res.objective_label
    assert all(c.utility_now > 9 for c in res.candidates if math.isfinite(c.utility_now))


def test_seed_reproducible(snap):
    st = state_after(5, snap)
    a = run_refinement(snap, st, S.RefineRequest(limit=3, budget_ms=5000, scenarios=100), seed=9)
    b = run_refinement(snap, st, S.RefineRequest(limit=3, budget_ms=5000, scenarios=100), seed=9)
    if a.scenarios == b.scenarios:
        assert [c.marginal_utility for c in a.candidates] == [c.marginal_utility for c in b.candidates]
