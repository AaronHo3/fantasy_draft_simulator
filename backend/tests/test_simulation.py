import numpy as np

from app.demo.generate import generate_demo_snapshot
from app.draft.events import initial_state
from app.engine.categories import PRIM_IDX, PRIMITIVES
from app.engine.layer_a import standardized
from app.engine.opponents import build_demand, opponent_choice, rollout_draft, user_policy_choice
from app.engine.simulation import (
    SimConfig,
    category_outcomes,
    category_win_probabilities,
    objective,
    roto_objective,
    simulate_players_week,
    team_totals,
)
from app.league.config import DEFAULT_NINE_CATEGORIES, ScoringFormat, TieRule, demo_league_config

CATS = DEFAULT_NINE_CATEGORIES


def test_simulated_week_is_coherent_and_correlated():
    snap = generate_demo_snapshot()
    rng = np.random.default_rng(1)
    sims = simulate_players_week(rng, snap.per_game[:50], snap.games[:50], SimConfig(n_scenarios=300))
    assert sims.shape == (50, 300, len(PRIMITIVES))
    assert np.all(sims >= 0)
    assert np.all(sims[:, :, PRIM_IDX["FGM"]] <= sims[:, :, PRIM_IDX["FGA"]])
    assert np.all(sims[:, :, PRIM_IDX["FG3M"]] <= sims[:, :, PRIM_IDX["FGM"]])
    assert np.all(sims[:, :, PRIM_IDX["FTM"]] <= sims[:, :, PRIM_IDX["FTA"]])
    pts = sims[:, :, PRIM_IDX["PTS"]]
    assert np.allclose(
        pts, 2 * sims[:, :, PRIM_IDX["FGM"]] + sims[:, :, PRIM_IDX["FG3M"]] + sims[:, :, PRIM_IDX["FTM"]]
    )
    # mean weekly points ~ per-game × games/week × availability
    exp = snap.per_game[:50, PRIM_IDX["PTS"]] * 3.5 * snap.games[:50] / 82
    assert np.allclose(pts.mean(axis=1), exp, rtol=0.12, atol=1.5)
    # shared factor: within a player, PTS and REB covary positively across scenarios
    i = int(np.argmax(snap.per_game[:50, PRIM_IDX["MIN"]]))
    corr = np.corrcoef(pts[i], sims[i, :, PRIM_IDX["REB"]])[0, 1]
    assert corr > 0.1


def test_objectives_each_vs_most_vs_roto():
    out = np.array([[1, 1, 1, 1, 1, -1, -1, -1, -1], [1, 1, 1, 1, -1, -1, -1, -1, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0]])
    each = objective(out, ScoringFormat.h2h_each_category, TieRule())
    most = objective(out, ScoringFormat.h2h_most_categories, TieRule())
    assert list(each) == [5.0, 4.5, 4.5]
    assert list(most) == [1.0, 0.5, 0.5]
    probs = category_win_probabilities(out)
    assert probs[0] == np.float64(2 / 3 + 0.5 / 3)
    # roto: three teams, PTS only differs; TOV lower better
    tot = np.zeros((2, 3, len(PRIMITIVES)))
    tot[:, :, PRIM_IDX["PTS"]] = [[100, 200, 300], [100, 200, 300]]
    tot[:, :, PRIM_IDX["TOV"]] = [[30, 20, 10], [30, 20, 10]]
    tot[:, :, PRIM_IDX["FGA"]] = 10
    tot[:, :, PRIM_IDX["FGM"]] = [[3, 4, 5], [3, 4, 5]]
    tot[:, :, PRIM_IDX["FTA"]] = 10
    tot[:, :, PRIM_IDX["FTM"]] = [[5, 5, 5], [5, 5, 5]]
    r = roto_objective(tot, CATS)
    assert r[2] > r[1] > r[0]


def test_category_outcomes_zero_attempts_handled():
    a = np.zeros((1, len(PRIMITIVES)))
    b = np.zeros((1, len(PRIMITIVES)))
    b[0, PRIM_IDX["FTA"]] = 10
    b[0, PRIM_IDX["FTM"]] = 8
    o = category_outcomes(a, b, CATS, TieRule(zero_attempts="unknown"))
    assert o[0, 7] == 0  # FT_PCT unknown -> tie
    o2 = category_outcomes(a, b, CATS, TieRule(zero_attempts="loss"))
    assert o2[0, 7] == -1


def test_rollout_respects_uniqueness_schedule_and_common_random_numbers():
    snap = generate_demo_snapshot()
    league = demo_league_config()
    state = initial_state(league)
    st = standardized(snap, league)
    base = st.z_totals.sum(axis=1)
    demand = build_demand(snap, base)
    assert demand.label == "adp:demo"
    rng = np.random.default_rng(3)
    u = rng.random((2, len(state.schedule)))
    r1 = rollout_draft(snap, league, state.schedule, {}, frozenset(), base, demand, u[0])
    picks = list(r1.picks.values())
    assert len(picks) == 156 and len(set(picks)) == 156
    assert all(len(r) == 13 for r in r1.rosters.values())
    # same uniforms -> same opponent picks; different candidate for the user changes little upstream
    r2 = rollout_draft(snap, league, state.schedule, {}, frozenset(), base, demand, u[0])
    assert r2.picks == r1.picks
    r3 = rollout_draft(snap, league, state.schedule, {}, frozenset(), base, demand, u[1])
    assert r3.picks != r1.picks
    # forcing the user's first pick (overall 6) is honored
    cand = next(i for i in np.argsort(demand.key) if i not in picks[:5])
    r4 = rollout_draft(snap, league, state.schedule, {}, frozenset(), base, demand, u[0], forced={6: int(cand)})
    assert r4.picks[6] == cand
    # early stop
    r5 = rollout_draft(snap, league, state.schedule, {}, frozenset(), base, demand, u[0], stop_after_overall=18)
    assert max(r5.picks) == 18


def test_user_policy_fills_required_slot_when_picks_run_out():
    snap = generate_demo_snapshot()
    league = demo_league_config()
    positions = snap.positions()
    guards = [i for i, p in enumerate(snap.players) if p.eligible_positions == frozenset({"PG"})][:12]
    available = np.ones(snap.n, dtype=bool)
    base = snap.per_game[:, PRIM_IDX["PTS"]].copy()
    # make a PG the most valuable; with 1 pick left and C open the policy must take a C-eligible player
    choice = user_policy_choice(available, base, positions, guards, league, remaining_user_picks=1)
    assert "C" in snap.players[choice].eligible_positions


def test_opponent_choice_prefers_need_and_is_deterministic_in_u():
    snap = generate_demo_snapshot()
    st = standardized(snap, demo_league_config())
    demand = build_demand(snap, st.z_totals.sum(axis=1))
    order = np.argsort(demand.key)
    avail = np.ones(snap.n, dtype=bool)
    a = opponent_choice(avail, demand, snap.positions(), [], 0.3, order)
    b = opponent_choice(avail, demand, snap.positions(), [], 0.3, order)
    assert a == b
    # team totals helper
    sims = simulate_players_week(
        np.random.default_rng(0), snap.per_game[:20], snap.games[:20], SimConfig(n_scenarios=10)
    )
    t = team_totals(sims, [0, 1, 2], max_starters=2)
    assert t.shape == (10, len(PRIMITIVES))


def test_rollouts_respect_primary_position_caps():
    snap = generate_demo_snapshot()
    league = demo_league_config().model_copy(update={"position_caps": {"C": 2}})
    state = initial_state(league)
    st = standardized(snap, league)
    base = st.z_totals.sum(axis=1)
    demand = build_demand(snap, base)
    u = np.random.default_rng(5).random((1, len(state.schedule)))
    r = rollout_draft(snap, league, state.schedule, {}, frozenset(), base, demand, u[0])
    prim = snap.primary_positions()
    for roster in r.rosters.values():
        assert sum(1 for i in roster if prim[i] == "C") <= 2
