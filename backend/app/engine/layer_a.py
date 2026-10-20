"""Layer A: fast deterministic screening ranking over all available players.

Score = strategy-weighted standardized season value (projected totals = per-game × games)
      − slot-aware replacement value (the best compatible player expected to still be available at
        the user's next pick)
      + risk adjustment (documented uncertainty term, sign set by the risk preference)
Flags, not hidden bonuses, cover eligibility verification, infeasible completions and injuries.
All functions are pure; the standardization is cached per (snapshot, pool size).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from app.engine.categories import PRIM_IDX, Standardization, select_pool, standardize
from app.engine.lineup import assign_lineup, roster_slots, slot_accepts
from app.league.config import LeagueConfig
from app.league.strategy import RiskPreference, Strategy
from app.projections.snapshot import Snapshot

RISK_LAMBDA = {RiskPreference.conservative: -0.35, RiskPreference.neutral: 0.0, RiskPreference.aggressive: 0.35}
TIER_GAP = 0.35  # score units; candidates closer than this are reported as one tier
POOL_FACTOR = 1.2


@dataclass(frozen=True)
class Standardized:
    z_totals: np.ndarray  # [n, c] season-total z (availability-adjusted)
    z_per_game: np.ndarray  # [n, c] per-game z (intrinsic)
    sd_z: np.ndarray  # [n, c] sd of total z from projection uncertainty
    info: Standardization
    pool_mask: np.ndarray


_STD_CACHE: dict[tuple[str, int, str], Standardized] = {}


def standardized(snapshot: Snapshot, league: LeagueConfig, method: str = "mad") -> Standardized:
    n_pool = int(round(league.n_managers * league.roster_size * POOL_FACTOR))
    key = (snapshot.snapshot_id, n_pool, method)
    hit = _STD_CACHE.get(key)
    if hit is not None:
        return hit
    cats = league.categories
    tot = snapshot.totals()
    pool = select_pool(tot, cats, n_pool, method)
    z_tot, info = standardize(tot, cats, pool, method)
    pg = snapshot.per_game.copy()
    pg[:, PRIM_IDX["GP"]] = 1.0
    z_pg, _ = standardize(pg, cats, pool, method)
    # uncertainty of each total z: per-game sd × games / scale (ratio cats via impact sd approx)
    sd_tot = snapshot.per_game_sd * snapshot.games[:, None]
    sd_z = np.zeros_like(z_tot)
    for j, c in enumerate(cats):
        if c.kind.value == "ratio":
            sd = sd_tot[:, PRIM_IDX[c.numerator]]
        else:
            sd = sd_tot[:, PRIM_IDX[c.key]]
        sd_z[:, j] = sd / info.scales[j]
    res = Standardized(z_tot, z_pg, sd_z, info, pool)
    if len(_STD_CACHE) > 16:
        _STD_CACHE.clear()
    _STD_CACHE[key] = res
    return res


@dataclass(frozen=True)
class RankingContext:
    snapshot: Snapshot
    league: LeagueConfig
    strategy: Strategy
    drafted: frozenset[str]
    user_roster_ids: tuple[str, ...]
    remaining_user_picks: int
    picks_until_next: int | None  # other managers' picks before the user's next turn (survival hints)
    total_remaining_picks: int  # all managers
    replacement_horizon: int | None = None  # picks before the user's FOLLOWING turn (replacement pool)


@dataclass(frozen=True)
class Candidate:
    idx: int
    player_id: str
    score: float
    base_value: float
    replacement_value: float
    replacement_player_id: str | None
    slot: str | None  # starting slot the player would fill now, else None (bench/overflow)
    fills_open_starting_slot: bool
    completion_ok: bool
    risk_adjustment: float
    value_sd: float
    z: np.ndarray  # strategy-unweighted total z per category
    contributions: np.ndarray  # weighted contributions per category
    flags: tuple[str, ...]
    survival_hint: str  # qualitative, from ADP when available
    tier: int = 0


def marginal_weights(roster_z_total: np.ndarray, scale: float) -> np.ndarray:
    """Diminishing returns: the value of +1 z in a category is the slope of the win probability at
    the roster's current margin, Φ'(T/s)/Φ'(0) = exp(-(T/s)²/2): 1 at the line, small far ahead/behind."""
    t = np.asarray(roster_z_total, dtype=float) / max(scale, 1e-9)
    return np.exp(-0.5 * t * t)


@dataclass(frozen=True)
class LayerAResult:
    candidates: tuple[Candidate, ...]  # sorted by score desc (all available players)
    keys: tuple[str, ...]
    weights: np.ndarray  # effective weights used (strategy × marginal)
    marginal: np.ndarray  # per-category marginal value multipliers (1 = full value)
    roster_z: np.ndarray  # current roster z-total per category
    standardization: Standardization
    user_open_slots: tuple[str, ...]
    user_assignment_legal: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    def top(self, k: int) -> tuple[Candidate, ...]:
        return self.candidates[:k]


def demand_order(snapshot: Snapshot, fallback_value: np.ndarray) -> np.ndarray:
    """Players sorted by how soon the league is expected to draft them: ADP, then value."""
    adp = snapshot.adp
    has = np.isfinite(adp)
    key = np.where(has, adp, 10_000.0 - fallback_value)  # unknown ADP sorts after known, by value
    return np.argsort(key, kind="stable")


def _survival_hint(adp: float, picks_until_next: int | None, current_overall: int | None) -> str:
    if picks_until_next is None or current_overall is None:
        return "n/a"
    if not np.isfinite(adp):
        return "no ADP: proxy only"
    next_overall = current_overall + picks_until_next + 1
    if adp < current_overall - 6:
        return "well past ADP: value pick"
    if adp <= next_overall - 8:
        return "likely gone before your next pick"
    if adp <= next_overall + 4:
        return "borderline: may not survive"
    return "likely available at your next pick"


def rank_layer_a(ctx: RankingContext, current_overall: int | None = None) -> LayerAResult:  # noqa: C901
    snap, league, strat = ctx.snapshot, ctx.league, ctx.strategy
    st = standardized(snap, league)
    keys = tuple(c.key for c in league.categories)
    w_strat = np.asarray(strat.weight_vector(list(keys)))
    roster_idx0 = [snap.index[p] for p in ctx.user_roster_ids if p in snap.index]
    roster_z = st.z_totals[roster_idx0].sum(axis=0) if roster_idx0 else np.zeros(len(keys))
    marg = marginal_weights(roster_z, strat.roster_scale) if strat.roster_aware else np.ones(len(keys))
    w = w_strat * marg
    base = st.z_totals @ w
    contributions_all = st.z_totals * w[None, :]
    value_sd = np.sqrt(((st.sd_z * w[None, :]) ** 2).sum(axis=1))
    lam = RISK_LAMBDA[strat.risk]
    risk_adj = lam * value_sd

    n = snap.n
    available = np.ones(n, dtype=bool)
    for pid in ctx.drafted:
        i = snap.index.get(pid)
        if i is not None:
            available[i] = False
    if league.strict_eligibility:
        for i, p in enumerate(snap.players):
            if not p.eligibility_verified:
                available[i] = False

    # user roster and open slots
    roster_idx = [snap.index[p] for p in ctx.user_roster_ids if p in snap.index]
    positions = snap.positions()
    slots = roster_slots(league)
    n_start = len(league.starting_slots)
    roster_pos = [positions[i] for i in roster_idx]
    primaries = snap.primary_positions()
    cap_counts: dict[str, int] = {}
    for i in roster_idx:
        pp = primaries[i]
        if pp:
            cap_counts[pp] = cap_counts.get(pp, 0) + 1
    capped = {pos for pos, cap in league.position_caps.items() if cap_counts.get(pos, 0) >= cap}
    base_assign = assign_lineup(roster_pos, slots, n_start)
    open_start = [slots[j] for j in base_assign.open_slot_indices if j < n_start]
    open_any = [slots[j] for j in base_assign.open_slot_indices]

    # demand ordering for "who survives until my next pick"
    order = demand_order(snap, base)
    avail_order = [i for i in order if available[i]]
    horizon = ctx.replacement_horizon if ctx.replacement_horizon is not None else ctx.picks_until_next
    k = horizon if horizon is not None else 0
    survivors = avail_order[k:] if k < len(avail_order) else []
    generic_repl_idx = max(survivors, key=lambda i: base[i]) if survivors else None

    def slot_replacement(slot: str, exclude: int) -> int | None:
        best, best_v = None, -np.inf
        for i in survivors:
            if i != exclude and slot_accepts(slot, positions[i]) and base[i] > best_v:
                best, best_v = i, base[i]
        return best

    repl_cache: dict[str, int | None] = {}
    cands: list[Candidate] = []
    avail_positions = [positions[i] for i in range(n) if available[i]]
    for i in range(n):
        if not available[i]:
            continue
        p = snap.players[i]
        flags: list[str] = []
        if not p.eligibility_verified:
            flags.append("eligibility unverified")
        if not p.eligible_positions:
            flags.append("no eligible positions: cannot fill a slot")
        if p.injury_status and p.injury_status not in ("ACTIVE", None):
            flags.append(f"injury status {p.injury_status}")
        if p.is_rookie:
            flags.append("rookie: prior/projection only")
        src_i = snap.projection_source[i]
        if src_i in ("prior", "demo"):
            flags.append(f"projection source: {src_i}")
        if src_i.startswith("espn_rookie"):
            flags.append("rookie: ESPN projection discounted, no NBA history")
        if src_i.endswith("_returning"):
            flags.append("missed all of last season: games and rates discounted")
        over_cap = primaries[i] in capped
        if over_cap:
            flags.append(f"would exceed the {primaries[i]} cap ({league.position_caps[primaries[i]]})")
        # which slot would this player fill now?
        a = assign_lineup([*roster_pos, positions[i]], slots, n_start)
        my_j = a.assigned.get(len(roster_pos))
        slot = slots[my_j] if my_j is not None else None
        fills_start = my_j is not None and my_j < n_start
        completion_ok = True
        if ctx.remaining_user_picks - 1 >= 0:
            new_open = [slots[j] for j in a.open_slot_indices if j < n_start]
            if len(new_open) > ctx.remaining_user_picks - 1:
                completion_ok = False
                flags.append("would leave starting slots unfillable with remaining picks")
        if slot is None and ctx.remaining_user_picks > 0 and len(open_any) > 0:
            flags.append("does not fit any open slot")
        if fills_start and slot is not None:
            if slot not in repl_cache:
                repl_cache[slot] = slot_replacement(slot, -1)
            r_idx = repl_cache[slot]
            if r_idx == i:
                r_idx = slot_replacement(slot, i)
        else:
            r_idx = (
                generic_repl_idx
                if generic_repl_idx != i
                else (max((j for j in survivors if j != i), key=lambda j: base[j], default=None))
            )
        repl_v = float(base[r_idx]) if r_idx is not None else 0.0
        score = float(base[i] - repl_v + risk_adj[i])
        if over_cap:
            completion_ok = False
        if not completion_ok:
            score -= 5.0  # hard discouragement, still visible and flagged
        if slot is None and len(open_any) > 0:
            score -= 5.0
        adp = float(snap.adp[i])
        cands.append(
            Candidate(
                idx=i,
                player_id=p.player_id,
                score=score,
                base_value=float(base[i]),
                replacement_value=repl_v,
                replacement_player_id=snap.players[r_idx].player_id if r_idx is not None else None,
                slot=slot,
                fills_open_starting_slot=bool(fills_start),
                completion_ok=completion_ok,
                risk_adjustment=float(risk_adj[i]),
                value_sd=float(value_sd[i]),
                z=st.z_totals[i],
                contributions=contributions_all[i],
                flags=tuple(flags),
                survival_hint=_survival_hint(adp, ctx.picks_until_next, current_overall),
            )
        )
    cands.sort(key=lambda c: (-c.score, c.player_id))
    # tiers: consecutive candidates closer than TIER_GAP share a tier
    tiered: list[Candidate] = []
    tier = 1
    for j, c in enumerate(cands):
        if j > 0 and cands[j - 1].score - c.score > TIER_GAP:
            tier += 1
        tiered.append(Candidate(**{**c.__dict__, "tier": tier}))
    notes = []
    if not any(np.isfinite(snap.adp)):
        notes.append("No ADP in this snapshot: survival hints use value order (proxy).")
    if ctx.picks_until_next is None:
        notes.append("Draft complete or user has no further picks; replacement = best available.")
    del avail_positions
    return LayerAResult(
        tuple(tiered), keys, w, marg, roster_z, st.info, tuple(open_start), base_assign.legal, tuple(notes)
    )


@lru_cache(maxsize=1)
def _noop() -> None:  # keeps lru_cache import meaningful for future memoization hooks
    return None
