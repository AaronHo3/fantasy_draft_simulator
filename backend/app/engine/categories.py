"""Nine-category mathematics on NumPy arrays.

Conventions:
- A *stat matrix* is ``float64[n_players, len(PRIMITIVES)]`` in PRIMITIVES column order. Its rows
  may hold per-game rates or period totals; the functions here do not care, except that ratio
  categories are always recomputed from the makes/attempts columns.
- Functions are pure: they return new arrays and never mutate inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.league.config import CategoryDef, CategoryKind, TieRule

PRIMITIVES: tuple[str, ...] = (
    "MIN",
    "GP",
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "FG3M",
    "FG3A",
    "FGM",
    "FGA",
    "FTM",
    "FTA",
    "TOV",
)
PRIM_IDX: dict[str, int] = {k: i for i, k in enumerate(PRIMITIVES)}
COUNTING_CATEGORY_PRIMITIVES = ("PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV")
MAD_TO_SIGMA = 1.4826


def empty_matrix(n: int) -> np.ndarray:
    return np.zeros((n, len(PRIMITIVES)), dtype=np.float64)


def totals(matrix: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """Sum rows of a stat matrix, optionally weighting each row (e.g. counted games)."""
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim == 1:
        m = m[None, :]
    if weights is None:
        return m.sum(axis=0)
    w = np.asarray(weights, dtype=np.float64).reshape(-1, 1)
    return (m * w).sum(axis=0)


def ratio(numerator: float, denominator: float) -> float | None:
    """sum(makes)/sum(attempts); None when there are no attempts (never a fabricated value)."""
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def category_values(total_row: np.ndarray, categories: list[CategoryDef]) -> dict[str, float | None]:
    """Category values for one team/period from its summed primitives."""
    out: dict[str, float | None] = {}
    for c in categories:
        if c.kind == CategoryKind.ratio:
            out[c.key] = ratio(total_row[PRIM_IDX[c.numerator]], total_row[PRIM_IDX[c.denominator]])
        else:
            out[c.key] = float(total_row[PRIM_IDX[c.key]])
    return out


def ratio_impact(makes: np.ndarray, attempts: np.ndarray, benchmark_rate: float) -> np.ndarray:
    """Volume-sensitive percentage impact: makes - b * attempts (positive helps the team rate)."""
    return np.asarray(makes, dtype=np.float64) - benchmark_rate * np.asarray(attempts, dtype=np.float64)


def pool_benchmark_rate(makes: np.ndarray, attempts: np.ndarray, pool_mask: np.ndarray) -> float:
    a = float(np.asarray(attempts)[pool_mask].sum())
    if a <= 0:
        return 0.0
    return float(np.asarray(makes)[pool_mask].sum()) / a


def robust_center_scale(x: np.ndarray, method: str = "mad") -> tuple[float, float]:
    """Center/scale of a pool. ``mad``: median and 1.4826*MAD; ``std``: mean and std.

    Falls back to std (then to 1.0) when the MAD is zero, so no category explodes.
    """
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return 0.0, 1.0
    if method == "mad":
        center = float(np.median(x))
        scale = MAD_TO_SIGMA * float(np.median(np.abs(x - center)))
        if scale <= 1e-12:
            scale = float(np.std(x))
    else:
        center = float(np.mean(x))
        scale = float(np.std(x))
    if scale <= 1e-12:
        scale = 1.0
    return center, scale


@dataclass(frozen=True)
class Standardization:
    keys: tuple[str, ...]
    centers: np.ndarray
    scales: np.ndarray
    benchmark_rates: dict[str, float]
    pool_size: int
    method: str

    def to_dict(self) -> dict:
        return {
            "keys": list(self.keys),
            "centers": [float(c) for c in self.centers],
            "scales": [float(s) for s in self.scales],
            "benchmark_rates": dict(self.benchmark_rates),
            "pool_size": self.pool_size,
            "method": self.method,
        }


def raw_category_matrix(
    matrix: np.ndarray, categories: list[CategoryDef], benchmark_rates: dict[str, float]
) -> np.ndarray:
    """Per-player raw category quantities: counting stats as-is, ratios as impact, TOV sign kept."""
    m = np.asarray(matrix, dtype=np.float64)
    cols = []
    for c in categories:
        if c.kind == CategoryKind.ratio:
            cols.append(
                ratio_impact(m[:, PRIM_IDX[c.numerator]], m[:, PRIM_IDX[c.denominator]], benchmark_rates[c.key])
            )
        else:
            cols.append(m[:, PRIM_IDX[c.key]])
    return np.column_stack(cols) if cols else np.zeros((m.shape[0], 0))


def select_pool(matrix: np.ndarray, categories: list[CategoryDef], n_pool: int, method: str = "mad") -> np.ndarray:
    """Two-pass fantasy-relevant pool: standardize over everyone, take the top n_pool by unweighted
    value, so replacement-level nobodies do not define the scale."""
    n = matrix.shape[0]
    all_mask = np.ones(n, dtype=bool)
    z, _ = standardize(matrix, categories, all_mask, method)
    first = z.sum(axis=1)
    n_pool = int(min(max(n_pool, 1), n))
    idx = np.argsort(-first, kind="stable")[:n_pool]
    mask = np.zeros(n, dtype=bool)
    mask[idx] = True
    return mask


def standardize(
    matrix: np.ndarray, categories: list[CategoryDef], pool_mask: np.ndarray, method: str = "mad"
) -> tuple[np.ndarray, Standardization]:
    """Standardized category values for all rows using center/scale from the pool rows.

    Lower-is-better categories (TOV) are negated so that higher z is always better.
    """
    m = np.asarray(matrix, dtype=np.float64)
    pool_mask = np.asarray(pool_mask, dtype=bool)
    rates: dict[str, float] = {}
    for c in categories:
        if c.kind == CategoryKind.ratio:
            rates[c.key] = pool_benchmark_rate(m[:, PRIM_IDX[c.numerator]], m[:, PRIM_IDX[c.denominator]], pool_mask)
    raw = raw_category_matrix(m, categories, rates)
    centers = np.zeros(raw.shape[1])
    scales = np.ones(raw.shape[1])
    z = np.zeros_like(raw)
    for j, c in enumerate(categories):
        center, scale = robust_center_scale(raw[pool_mask, j], method)
        centers[j], scales[j] = center, scale
        col = (raw[:, j] - center) / scale
        z[:, j] = col if c.higher_is_better else -col
    info = Standardization(tuple(c.key for c in categories), centers, scales, rates, int(pool_mask.sum()), method)
    return z, info


def weighted_value(z: np.ndarray, weights: np.ndarray | list[float]) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64)
    return np.asarray(z, dtype=np.float64) @ w


# --- matchup scoring -------------------------------------------------------------------------


def compare_categories(
    a_totals: np.ndarray, b_totals: np.ndarray, categories: list[CategoryDef], tie_rule: TieRule
) -> list[int | None]:
    """Per-category outcome for team A vs team B: +1 win, 0 tie, -1 loss, None unknown."""
    va = category_values(a_totals, categories)
    vb = category_values(b_totals, categories)
    out: list[int | None] = []
    for c in categories:
        x, y = va[c.key], vb[c.key]
        if x is None or y is None:
            if tie_rule.zero_attempts == "tie":
                out.append(0)
            elif tie_rule.zero_attempts == "loss":
                out.append(-1 if x is None and y is not None else (1 if y is None and x is not None else 0))
            else:
                out.append(None)
            continue
        if abs(x - y) < 1e-12:
            out.append(0)
        else:
            better = x > y if c.higher_is_better else x < y
            out.append(1 if better else -1)
    return out


def each_category_score(outcomes: list[int | None], tie_rule: TieRule) -> float:
    """Each-category points for team A: wins + tie_value * ties (unknowns count zero)."""
    s = 0.0
    for o in outcomes:
        if o == 1:
            s += 1.0
        elif o == 0:
            s += tie_rule.each_category_tie_value
    return s


def most_categories_result(outcomes: list[int | None]) -> str:
    """'win' | 'loss' | 'tie' for team A under most-categories rules (ties count for neither)."""
    wins = sum(1 for o in outcomes if o == 1)
    losses = sum(1 for o in outcomes if o == -1)
    if wins > losses:
        return "win"
    if losses > wins:
        return "loss"
    return "tie"


def roto_points(team_totals: np.ndarray, categories: list[CategoryDef]) -> np.ndarray:
    """Rotisserie rank points, shape [n_teams, n_categories]. Best team gets n_teams points, ties
    share the average of the tied ranks. Unknown ratio values (no attempts) rank last."""
    t = np.asarray(team_totals, dtype=np.float64)
    n = t.shape[0]
    pts = np.zeros((n, len(categories)))
    for j, c in enumerate(categories):
        vals = []
        for i in range(n):
            v = category_values(t[i], [c])[c.key]
            vals.append(-np.inf if v is None else (v if c.higher_is_better else -v))
        arr = np.array(vals)
        order = np.argsort(-arr, kind="stable")
        ranks = np.empty(n)
        k = 0
        while k < n:
            m = k
            while m + 1 < n and arr[order[m + 1]] == arr[order[k]]:
                m += 1
            avg_points = n - (k + m) / 2.0
            for q in range(k, m + 1):
                ranks[order[q]] = avg_points
            k = m + 1
        pts[:, j] = ranks
    return pts
