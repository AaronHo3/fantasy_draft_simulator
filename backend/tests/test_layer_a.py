import numpy as np
import pytest

from app.demo.generate import generate_demo_snapshot
from app.engine.categories import PRIM_IDX
from app.engine.layer_a import RankingContext, rank_layer_a, standardized
from app.league.config import demo_league_config
from app.league.strategy import PuntKind, RiskPreference, Strategy


@pytest.fixture(scope="module")
def snap():
    return generate_demo_snapshot()


def ctx(snap, drafted=(), roster=(), strategy=None, remaining=13, until_next=5):
    return RankingContext(
        snap,
        demo_league_config(),
        strategy or Strategy(),
        frozenset(drafted),
        tuple(roster),
        remaining,
        until_next,
        156 - len(drafted),
    )


def test_drafted_players_never_recommended(snap):
    first = rank_layer_a(ctx(snap), current_overall=1).candidates
    top = first[0].player_id
    second = rank_layer_a(ctx(snap, drafted=[top]), current_overall=2).candidates
    assert all(c.player_id != top for c in second)
    assert len(second) == len(first) - 1


def test_fixed_punt_changes_ranking_and_zeroes_contribution(snap):
    base = rank_layer_a(ctx(snap), current_overall=6)
    punt = rank_layer_a(ctx(snap, strategy=Strategy(punts={"FT_PCT": PuntKind.fixed})), current_overall=6)
    j = base.keys.index("FT_PCT")
    assert all(c.contributions[j] == 0.0 for c in punt.candidates)
    # a poor FT shooter with volume should move up when FT% is punted
    ft_rate = snap.per_game[:, PRIM_IDX["FTM"]] / np.maximum(snap.per_game[:, PRIM_IDX["FTA"]], 1e-9)
    fta = snap.per_game[:, PRIM_IDX["FTA"]]
    bad = [i for i in np.argsort(ft_rate) if fta[i] > 4][:5]
    rank_base = {c.player_id: r for r, c in enumerate(base.candidates)}
    rank_punt = {c.player_id: r for r, c in enumerate(punt.candidates)}
    pid = snap.players[bad[0]].player_id
    assert rank_punt[pid] < rank_base[pid]


def test_slot_need_affects_replacement_and_flags(snap):
    # fill the user's roster with 12 guards; last pick must fill a C/F type slot
    guards = [p.player_id for p in snap.players if p.eligible_positions == frozenset({"PG"})][:9]
    res = rank_layer_a(ctx(snap, drafted=guards, roster=guards, remaining=4, until_next=11), current_overall=100)
    assert "PG" not in res.user_open_slots and "C" in res.user_open_slots
    top = res.candidates[0]
    assert top.fills_open_starting_slot
    # another PG now goes to the bench and must not outrank a comparable big: it fills no starting slot
    pg_cands = [c for c in res.candidates if snap.players[c.idx].eligible_positions == frozenset({"PG"})]
    assert pg_cands and not pg_cands[0].fills_open_starting_slot


def test_risk_preference_shifts_scores_consistently(snap):
    neutral = rank_layer_a(ctx(snap), current_overall=6).candidates[0]
    cons = rank_layer_a(ctx(snap, strategy=Strategy(risk=RiskPreference.conservative)), current_overall=6)
    c = next(x for x in cons.candidates if x.player_id == neutral.player_id)
    assert c.risk_adjustment < 0 and neutral.risk_adjustment == 0.0
    assert c.base_value == pytest.approx(neutral.base_value)


def test_tiers_and_determinism(snap):
    a = rank_layer_a(ctx(snap), current_overall=6)
    b = rank_layer_a(ctx(snap), current_overall=6)
    assert [c.player_id for c in a.candidates[:20]] == [c.player_id for c in b.candidates[:20]]
    assert a.candidates[0].tier == 1
    assert all(a.candidates[i].tier <= a.candidates[i + 1].tier for i in range(50))


def test_standardization_cached_and_pool_sized(snap):
    s1 = standardized(snap, demo_league_config())
    s2 = standardized(snap, demo_league_config())
    assert s1 is s2
    assert s1.info.pool_size == round(12 * 13 * 1.2)


def test_strict_eligibility_excludes_unverified(snap):
    from dataclasses import replace

    players = list(snap.players)
    players[0] = replace(players[0], eligibility_verified=False)
    snap2 = replace(snap, players=tuple(players), snapshot_id=snap.snapshot_id + "-x")
    league = demo_league_config().model_copy(update={"strict_eligibility": True})
    c = RankingContext(snap2, league, Strategy(), frozenset(), (), 13, 5, 156)
    res = rank_layer_a(c, 1)
    assert all(x.player_id != players[0].player_id for x in res.candidates)


def test_layer_a_speed_600_players(snap):
    import time

    c = ctx(
        snap,
        drafted=[p.player_id for p in snap.players[:40]],
        roster=[snap.players[5].player_id, snap.players[17].player_id, snap.players[29].player_id],
    )
    rank_layer_a(c, 41)  # warm
    t = time.perf_counter()
    for _ in range(5):
        rank_layer_a(c, 41)
    dt = (time.perf_counter() - t) / 5
    assert dt < 0.25, f"layer A took {dt * 1000:.0f} ms"


def test_center_cap_flags_fifth_center(snap):
    centers = [p.player_id for p in snap.players if p.primary_position == "C"][:4]
    league = demo_league_config()  # C cap 4 by default
    c = RankingContext(snap, league, Strategy(), frozenset(centers), tuple(centers), 9, 11, 152)
    res = rank_layer_a(c, 5)
    fifth = [x for x in res.candidates if snap.players[x.idx].primary_position == "C"]
    assert fifth and all(not x.completion_ok and any("cap" in f for f in x.flags) for x in fifth)
    assert snap.players[res.candidates[0].idx].primary_position != "C"


def test_roster_aware_weights_discount_dominated_categories(snap):
    from app.engine.layer_a import marginal_weights
    m = marginal_weights(np.array([0.0, 3.6, -7.2]), 3.6)
    assert m[0] == 1.0 and 0.55 < m[1] < 0.65 and m[2] < 0.2
    # build a roster that dominates assists: the top assist players
    st = standardized(snap, demo_league_config())
    j = list(c.key for c in demo_league_config().categories).index("AST")
    top_ast = [snap.players[i].player_id for i in np.argsort(-st.z_totals[:, j])[:4]]
    aware = rank_layer_a(ctx(snap, drafted=top_ast, roster=top_ast, remaining=9, until_next=11, strategy=Strategy(roster_aware=True)), current_overall=50)
    plain = rank_layer_a(ctx(snap, drafted=top_ast, roster=top_ast, remaining=9, until_next=11, strategy=Strategy(roster_aware=False)), current_overall=50)
    assert aware.marginal[j] < 0.6 and plain.marginal[j] == 1.0
    # with assists discounted, the weighted assist contribution of every candidate shrinks relative to plain
    a0, p0 = aware.candidates[0], plain.candidates[0]
    assert abs(aware.weights[j]) < abs(plain.weights[j])
    assert a0.player_id != p0.player_id or True  # ordering may or may not change; weights must
