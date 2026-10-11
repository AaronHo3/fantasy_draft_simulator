import numpy as np
import pytest

from app.engine.categories import (
    PRIM_IDX,
    PRIMITIVES,
    category_values,
    compare_categories,
    each_category_score,
    empty_matrix,
    most_categories_result,
    ratio,
    ratio_impact,
    robust_center_scale,
    roto_points,
    select_pool,
    standardize,
    totals,
    weighted_value,
)
from app.league.config import DEFAULT_NINE_CATEGORIES, TieRule
from app.league.strategy import PuntKind, Strategy

CATS = DEFAULT_NINE_CATEGORIES


def row(**kw):
    r = np.zeros(len(PRIMITIVES))
    for k, v in kw.items():
        r[PRIM_IDX[k]] = v
    return r


def test_percentages_are_weighted_by_attempts_not_averaged():
    # 50% on 2 attempts and 90% on 100 attempts -> 91/102 = 0.892, not 0.70
    a = row(FGM=1, FGA=2)
    b = row(FGM=90, FGA=100)
    t = totals(np.vstack([a, b]))
    vals = category_values(t, CATS)
    assert vals["FG_PCT"] == pytest.approx(91 / 102)
    assert vals["FG_PCT"] != pytest.approx(0.70)


def test_zero_attempts_is_none_not_a_win():
    assert ratio(0, 0) is None
    vals = category_values(row(FTM=0, FTA=0), CATS)
    assert vals["FT_PCT"] is None
    out = compare_categories(row(FTM=0, FTA=0, PTS=10), row(FTM=5, FTA=10, PTS=5), CATS, TieRule())
    assert out[CATS.index(next(c for c in CATS if c.key == "FT_PCT"))] is None
    assert out[0] == 1  # PTS still compared


def test_ratio_impact_is_volume_sensitive():
    b = 0.47
    low = ratio_impact(np.array([5.0]), np.array([10.0]), b)[0]  # 50% on 10
    high = ratio_impact(np.array([50.0]), np.array([100.0]), b)[0]  # 50% on 100
    assert high > low > 0
    assert ratio_impact(np.array([4.0]), np.array([10.0]), b)[0] < 0


def test_turnovers_lower_is_better_in_standardization_and_matchups():
    m = empty_matrix(3)
    m[0] = row(TOV=1, PTS=10, FGA=1, FGM=0.5, FTA=1, FTM=0.5)
    m[1] = row(TOV=3, PTS=10, FGA=1, FGM=0.5, FTA=1, FTM=0.5)
    m[2] = row(TOV=5, PTS=10, FGA=1, FGM=0.5, FTA=1, FTM=0.5)
    z, info = standardize(m, CATS, np.ones(3, dtype=bool))
    j = info.keys.index("TOV")
    assert z[0, j] > z[1, j] > z[2, j]
    out = compare_categories(row(TOV=10), row(TOV=12), CATS, TieRule())
    assert out[info.keys.index("TOV")] == 1


def test_punt_weights_zero_out_fixed_and_reduce_soft():
    s = Strategy(punts={"FT_PCT": PuntKind.fixed, "TOV": PuntKind.soft}, weights={"AST": 1.5})
    keys = [c.key for c in CATS]
    w = s.weight_vector(keys)
    assert w[keys.index("FT_PCT")] == 0.0
    assert w[keys.index("TOV")] == pytest.approx(0.35)
    assert w[keys.index("AST")] == 1.5
    assert w[keys.index("PTS")] == 1.0
    z = np.ones((2, len(keys)))
    z[1, keys.index("FT_PCT")] = 100.0  # huge FT% value should not matter when punted
    v = weighted_value(z, w)
    assert v[0] == pytest.approx(v[1])


def test_each_vs_most_categories_semantics_differ():
    # A wins 5 narrowly, loses 4 -> most-categories win, each-category 5 points
    out = [1, 1, 1, 1, 1, -1, -1, -1, -1]
    assert most_categories_result(out) == "win"
    assert each_category_score(out, TieRule()) == 5.0
    # with ties: 4 wins, 4 losses, 1 tie -> matchup tie; each-category gets 4.5 with half credit
    out2 = [1, 1, 1, 1, -1, -1, -1, -1, 0]
    assert most_categories_result(out2) == "tie"
    assert each_category_score(out2, TieRule(each_category_tie_value=0.5)) == 4.5
    assert each_category_score(out2, TieRule(each_category_tie_value=0.0)) == 4.0
    # 4 wins 3 losses 2 ties -> still a most-categories win (ties count for nobody)
    assert most_categories_result([1, 1, 1, 1, -1, -1, -1, 0, 0]) == "win"


def test_roto_points_ranks_with_ties_and_direction():
    t = np.vstack(
        [
            row(PTS=100, TOV=10, FGM=5, FGA=10, FTM=1, FTA=1),
            row(PTS=200, TOV=10, FGM=6, FGA=10, FTM=1, FTA=1),
            row(PTS=300, TOV=5, FGM=0, FGA=0, FTM=1, FTA=1),
        ]
    )
    pts = roto_points(t, CATS)
    keys = [c.key for c in CATS]
    assert list(pts[:, keys.index("PTS")]) == [1.0, 2.0, 3.0]
    assert list(pts[:, keys.index("TOV")]) == [1.5, 1.5, 3.0]  # fewest TOV best; tie shares
    assert pts[2, keys.index("FG_PCT")] == 1.0  # no attempts ranks last


def test_robust_scale_falls_back_when_mad_is_zero():
    c, s = robust_center_scale(np.array([1.0, 1.0, 1.0, 5.0]))
    assert c == 1.0 and s > 0


def test_pool_selection_excludes_scrubs_from_scale():
    rng = np.random.default_rng(0)
    m = empty_matrix(300)
    m[:, PRIM_IDX["PTS"]] = np.concatenate([rng.normal(20, 4, 150), rng.normal(2, 1, 150)])
    m[:, PRIM_IDX["FGA"]] = 10
    m[:, PRIM_IDX["FGM"]] = 4.5
    m[:, PRIM_IDX["FTA"]] = 4
    m[:, PRIM_IDX["FTM"]] = 3
    pool = select_pool(m, CATS, 150)
    assert pool.sum() == 150
    z_pool, info = standardize(m, CATS, pool)
    z_all, info_all = standardize(m, CATS, np.ones(300, dtype=bool))
    j = info.keys.index("PTS")
    assert info.centers[j] > 15  # pool center is among rotation players
    assert info_all.centers[j] < 15


def test_standardize_does_not_mutate_input():
    m = empty_matrix(2)
    m[0] = row(PTS=10, FGA=10, FGM=5, FTA=2, FTM=1)
    m[1] = row(PTS=20, FGA=10, FGM=5, FTA=2, FTM=1)
    before = m.copy()
    standardize(m, CATS, np.ones(2, dtype=bool))
    assert np.array_equal(m, before)
