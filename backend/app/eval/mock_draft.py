"""Paired mock-draft evaluation on a completed season (retrospective, labeled as such).

Projections are fit only on seasons before ``target``; every strategy drafts from the same seat with
the same opponent randomness (common random numbers); completed rosters are scored with what the
players actually did in ``target`` under the league's each-category rule. Opponents draft by a
value-order demand model with positional need and noise (no historical ADP is available).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from app.api import schemas as S
from app.draft.events import DraftState, Event, EventType, apply, initial_state, now_iso
from app.engine.categories import PRIM_IDX, PRIMITIVES, compare_categories, each_category_score, totals
from app.engine.layer_a import RankingContext, rank_layer_a, standardized
from app.engine.opponents import build_demand, cap_mask, opponent_choice
from app.identity.players import Player
from app.league.config import LeagueConfig, Manager, ScoringFormat, demo_league_config
from app.league.strategy import Strategy
from app.projections.baseline import BaselineConfig, naive_last_season, project_baseline
from app.projections.snapshot import Snapshot, content_hash
from app.recommend.refine import run_refinement
from app.settings import REPO_DIR

REALIZED_COLS = {"GP": "gp", "MIN": "min", "PTS": "pts", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk",
                 "FG3M": "fg3m", "FG3A": "fg3a", "FGM": "fgm", "FGA": "fga", "FTM": "ftm", "FTA": "fta", "TOV": "tov"}


@dataclass(frozen=True)
class Holdout:
    snapshot: Snapshot  # baseline projections fit before target
    naive_snapshot: Snapshot  # last season's per-game numbers as the projection
    realized: np.ndarray  # [n, P] actual season totals in target (zeros when the player did not play)
    target: str
    notes: tuple[str, ...]


def build_holdout(data_dir: Path, target: str = "2025-26", cfg=None, user_cfg=None, user_model: str | None = None) -> Holdout:
    """``cfg`` projects the opponents' (and default) snapshot; ``user_cfg`` builds an alternative snapshot
    for the user's seat (model-vs-model experiments) stored in ``naive_snapshot``'s slot when given."""
    nd = Path(data_dir) / "nba" / "normalized"
    tot = pd.read_parquet(nd / "season_totals.parquet")
    logs = pd.read_parquet(nd / "game_logs.parquet")
    from app.projections.learned import normalize_games

    tot = normalize_games(tot, logs)
    espn = pd.read_parquet(nd / "espn_players.parquet").set_index("espn_id")
    cw = pd.read_parquet(nd / "crosswalk.parquet")
    link = {int(r.nba_id): int(r.espn_id) for r in cw.itertuples() if pd.notna(r.nba_id) and pd.notna(r.espn_id)}
    positions = pd.Series({nid: espn.loc[eid, "primary_position"] for nid, eid in link.items()
                           if isinstance(espn.loc[eid, "primary_position"], str)})
    base = project_baseline(tot, target, positions, cfg, game_logs=logs).table.set_index("nba_id")
    if user_model:
        from app.projections.learned import project_learned, with_games
        parts = user_model.split(":")
        kind = parts[0]
        rich = "rich" in parts[1:]
        gp_mode = next((x for x in parts[1:] if x in ("flat", "last", "avg3", "shrunk", "model")), "model")
        if kind == "mix":
            from app.projections.learned import blend_tables
            tab = blend_tables(project_learned(tot, logs, target, kind="ridge", rich=False),
                               project_learned(tot, logs, target, kind="ens", rich=True), 0.5)
        else:
            tab = project_learned(tot, logs, target, kind=kind, rich=rich)
        naive = with_games(tab, gp_mode, tot, target).set_index("nba_id")
        user_cfg = user_cfg or BaselineConfig()  # marks the alternative slot as a model, not last-season numbers
    else:
        naive = (project_baseline(tot, target, positions, user_cfg, game_logs=logs).table if user_cfg is not None
                 else naive_last_season(tot, target)).set_index("nba_id")
    actual = tot[(tot["season"] == target) & (tot["season_type"] == "Regular Season")].set_index("nba_id")
    ids = [int(i) for i in base.index if int(i) in link and int(i) in naive.index]
    players, pg, sd, npg, real = [], [], [], [], []
    for nid in ids:
        e = espn.loc[link[nid]]
        elig = frozenset(json.loads(e["eligible_positions_json"]))
        if not elig:
            continue
        row = base.loc[nid]
        players.append(Player(player_id=f"nba:{nid}", name=str(e["name"]), team=str(e["team"]) if pd.notna(e["team"]) else None,
                              nba_id=nid, espn_id=link[nid], primary_position=e["primary_position"] if pd.notna(e["primary_position"]) else None,
                              eligible_positions=elig, eligibility_source="espn", eligibility_verified=True))
        pg.append([float(row[f"pg_{k}"]) for k in PRIMITIVES])
        sd.append([float(row[f"sd_{k}"]) for k in PRIMITIVES])
        nrow = naive.loc[nid]
        npg.append([float(nrow[f"pg_{k}"]) if f"pg_{k}" in nrow else 0.0 for k in PRIMITIVES])
        if user_cfg is not None:
            sd[-1] = [float(nrow[f"sd_{k}"]) for k in PRIMITIVES]
        if nid in actual.index:
            a = actual.loc[nid]
            real.append([float(a[REALIZED_COLS[k]]) for k in PRIMITIVES])
        else:
            real.append([0.0] * len(PRIMITIVES))
    n = len(players)
    pg_a, sd_a, npg_a, real_a = np.array(pg), np.array(sd), np.array(npg), np.array(real)
    created = datetime.now(UTC).isoformat(timespec="seconds")
    nan = np.full(n, np.nan)
    snap = Snapshot(f"holdout-{content_hash(pg_a)}", f"Holdout {target}: baseline fit on prior seasons", "nba", target, created,
                    tuple(players), pg_a, sd_a, nan.copy(), nan.copy(), tuple(["baseline"] * n))
    naive_snap = Snapshot(f"holdout-alt-{content_hash(npg_a)}", f"Holdout {target}: {'alternative model' if user_cfg else 'last-season numbers'}",
                          "nba", target, created, tuple(players), npg_a, np.abs(npg_a) * 0.2, nan.copy(), nan.copy(),
                          tuple([("alt" if user_cfg else "naive")] * n))
    notes = (
        f"Universe: {n} players with NBA history before {target} and an ESPN eligibility link (2025 rookies excluded: no leak-free projection exists for them).",
        "Eligibility comes from the current ESPN snapshot (not the preseason of the target year).",
        "Opponents draft by value order with positional need and noise; no historical ADP is available, so draft dynamics are a proxy.",
        "Players who did not play in the target season score zero (injuries count against every strategy equally).",
        "Counted starters: top 10 roster players by realized minutes (weekly-lock proxy).",
    )
    return Holdout(snap, naive_snap, real_a, target, notes)


# --- scoring -----------------------------------------------------------------------------------

def realized_team_totals(h: Holdout, roster_idx: list[int], n_start: int) -> np.ndarray:
    if not roster_idx:
        return np.zeros(len(PRIMITIVES))
    idx = sorted(roster_idx, key=lambda i: -h.realized[i, PRIM_IDX["MIN"]])[:n_start]
    return totals(h.realized[idx])


def score_league(h: Holdout, league: LeagueConfig, rosters: dict[str, list[int]]) -> dict[str, dict[str, float]]:
    """Per manager: mean categories won per matchup vs. every other team, matchup win rate, league rank."""
    n_start = len(league.starting_slots)
    team_tot = {m: realized_team_totals(h, r, n_start) for m, r in rosters.items()}
    out: dict[str, dict[str, float]] = {}
    for a in rosters:
        cats, wins = [], []
        for b in rosters:
            if a == b:
                continue
            o = compare_categories(team_tot[a], team_tot[b], league.categories, league.tie_rule)
            c = each_category_score(o, league.tie_rule)
            cats.append(c)
            wins.append(1.0 if c > 4.5 else 0.5 if c == 4.5 else 0.0)
        out[a] = {"cats_won": float(np.mean(cats)), "matchup_win_rate": float(np.mean(wins))}
    order = sorted(out, key=lambda m: -out[m]["cats_won"])
    for r, m in enumerate(order, start=1):
        out[m]["rank"] = float(r)
    return out


# --- strategies ----------------------------------------------------------------------------------

@dataclass
class DraftRun:
    strategy: str
    seat: int
    seed: int
    rosters: dict[str, list[int]]
    user_picks: list[int]
    seconds: float


def _apply_pick(state: DraftState, idx: int, snap: Snapshot, seq: int) -> DraftState:
    cp = state.current_pick
    assert cp is not None
    ev = Event(seq, EventType.pick_committed, {"player_id": snap.players[idx].player_id, "overall": cp.overall, "manager_id": cp.manager_id},
               f"k{seq}", now_iso())
    return apply(state, ev)


def run_draft(h: Holdout, league: LeagueConfig, strategy: str, seed: int, u: np.ndarray, budget_ms: int = 2000,
              fast_strategy: Strategy | None = None) -> DraftRun:
    """One full draft. ``u`` is the shared uniform vector (one per schedule pick) for opponent noise."""
    snap = h.snapshot
    state = initial_state(league, fast_strategy or Strategy(sim_budget_ms=budget_ms))
    uid = league.user_manager_id
    st = standardized(snap, league)
    proxy_value = st.z_totals.sum(axis=1)
    demand = build_demand(snap, proxy_value)
    order = np.argsort(demand.key, kind="stable")
    primaries = snap.primary_positions()
    positions = snap.positions()
    by_pos = {pos: np.array([i for i, pp in enumerate(primaries) if pp == pos], dtype=int) for pos in league.position_caps}
    naive_value = standardized(h.naive_snapshot, league).z_totals.sum(axis=1)
    available = np.ones(snap.n, dtype=bool)
    rosters: dict[str, list[int]] = {m.id: [] for m in league.managers}
    user_picks: list[int] = []
    t0 = time.perf_counter()
    seq = 1
    from app.engine.lineup import assign_lineup, roster_slots, slot_accepts
    slots, n_start = roster_slots(league), len(league.starting_slots)
    while state.current_pick is not None:
        cp = state.current_pick
        m = cp.manager_id
        legal = cap_mask(available, rosters[m], primaries, league.position_caps, by_pos)
        if m != uid or strategy == "adp_bot":
            a = assign_lineup([positions[i] for i in rosters[m]], slots, n_start)
            open_slots = [slots[j] for j in a.open_slot_indices if j < n_start]
            idx = opponent_choice(legal, demand, positions, open_slots, float(u[cp.overall - 1]), order)
        elif strategy in ("static_value", "naive_last_season", "alt_model"):
            vals = proxy_value if strategy == "static_value" else naive_value
            cand = np.where(legal)[0]
            idx = int(cand[np.argmax(vals[cand])])
        elif strategy == "static_need":  # static value restricted to players that fill an open starting slot while any remain
            a = assign_lineup([positions[i] for i in rosters[m]], slots, n_start)
            open_slots = [slots[j] for j in a.open_slot_indices if j < n_start]
            cand = np.where(legal)[0]
            fit = [i for i in cand if any(slot_accepts(s, positions[i]) for s in open_slots)] if open_slots else list(cand)
            pool = fit or list(cand)
            idx = int(max(pool, key=lambda i: proxy_value[i]))
        elif strategy.startswith("fast"):
            scale = float(strategy.split("@")[1]) if "@" in strategy else state.strategy.roster_scale
            strat_fast = state.strategy.model_copy(update={"roster_aware": strategy != "fast_plain", "roster_scale": scale})
            ctx = RankingContext(snap, league, strat_fast, state.drafted_player_ids, tuple(r.player_id for r in state.roster(uid)),
                                 state.remaining_picks_for(uid), state.picks_until_user_turn(),
                                 sum(1 for p in state.schedule if p.overall not in state.picks),
                                 (state.user_following_pick().overall - cp.overall - 1) if state.user_following_pick() else None)
            res = rank_layer_a(ctx, cp.overall)
            idx = res.candidates[0].idx
        elif strategy == "refined":
            ref = run_refinement(snap, state, S.RefineRequest(limit=6, budget_ms=budget_ms), seed * 7919 + cp.overall)
            pid = ref.highlighted_player_id
            if pid is None:
                ctx = RankingContext(snap, league, state.strategy, state.drafted_player_ids, tuple(r.player_id for r in state.roster(uid)),
                                     state.remaining_picks_for(uid), 0, 1, None)
                idx = rank_layer_a(ctx, cp.overall).candidates[0].idx
            else:
                idx = snap.index[pid]
        else:
            raise ValueError(strategy)
        available[idx] = False
        rosters[m].append(idx)
        if m == uid:
            user_picks.append(idx)
        seq += 1
        state = _apply_pick(state, idx, snap, seq)
    return DraftRun(strategy, league.managers.index(league.manager(uid)) + 1, seed, rosters, user_picks, time.perf_counter() - t0)


# --- experiment ----------------------------------------------------------------------------------

@dataclass
class Experiment:
    target: str
    seats: list[int]
    seeds: list[int]
    strategies: list[str]
    results: list[dict] = field(default_factory=list)  # one per (strategy, seat, seed)
    notes: list[str] = field(default_factory=list)


def run_experiment(data_dir: Path, seats: list[int], seeds: list[int], strategies: list[str],
                   refined_seats: list[int] | None = None, budget_ms: int = 2000, league: LeagueConfig | None = None,
                   log=print, refined_seeds: int | None = None, cfg=None, user_cfg=None, target: str = "2025-26",
                   user_model: str | None = None) -> Experiment:
    h = build_holdout(data_dir, target, cfg, user_cfg, user_model)
    base_league = league or demo_league_config()
    base_league = base_league.model_copy(update={"scoring_format": ScoringFormat.h2h_each_category})
    exp = Experiment(h.target, seats, seeds, strategies, notes=list(h.notes))
    for seed in seeds:
        rng = np.random.default_rng(seed)
        u = rng.random(base_league.n_managers * base_league.roster_size)
        for seat in seats:
            managers = [Manager(id=m.id, name=m.name, is_user=(i + 1 == seat)) for i, m in enumerate(base_league.managers)]
            league_s = base_league.model_copy(update={"managers": managers, "user_manager_id": managers[seat - 1].id})
            for strat in strategies:
                if strat == "refined" and refined_seats is not None and seat not in refined_seats:
                    continue
                if strat == "refined" and refined_seeds is not None and seed >= refined_seeds:
                    continue
                run = run_draft(h, league_s, strat, seed, u, budget_ms)
                scores = score_league(h, league_s, run.rosters)
                mine = scores[league_s.user_manager_id]
                exp.results.append({"strategy": strat, "seat": seat, "seed": seed, **mine, "seconds": round(run.seconds, 1),
                                    "picks": [h.snapshot.players[i].name for i in run.user_picks]})
                log(f"seed {seed} seat {seat:2d} {strat:18s} cats_won {mine['cats_won']:.2f} win% {mine['matchup_win_rate']:.2f} rank {mine['rank']:.0f} ({run.seconds:.0f}s)")
    return exp


def summarize(exp: Experiment) -> dict:
    df = pd.DataFrame(exp.results)
    out: dict = {"per_strategy": {}, "paired_vs": {}}
    for strat, g in df.groupby("strategy"):
        out["per_strategy"][strat] = {"n": int(len(g)), "cats_won": float(g["cats_won"].mean()), "win_rate": float(g["matchup_win_rate"].mean()),
                                      "rank": float(g["rank"].mean()), "top3_share": float((g["rank"] <= 3).mean())}
    key = ["seat", "seed"]
    for ref in ("adp_bot", "static_value"):
        if ref not in set(df["strategy"]):
            continue
        base = df[df["strategy"] == ref].set_index(key)
        out["paired_vs"][ref] = {}
        for strat, g in df.groupby("strategy"):
            if strat == ref:
                continue
            j = g.set_index(key).join(base, rsuffix="_ref", how="inner")
            if len(j) == 0:
                continue
            d = (j["cats_won"] - j["cats_won_ref"]).to_numpy()
            se = float(d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else float("nan")
            out["paired_vs"][ref][strat] = {"n_pairs": int(len(d)), "mean_diff_cats_won": float(d.mean()), "se": se,
                                            "wins": int((d > 0).sum()), "losses": int((d < 0).sum()), "ties": int((d == 0).sum()),
                                            "mean_diff_rank": float((j["rank"] - j["rank_ref"]).mean())}
    return out


def write_report(exp: Experiment, summary: dict, path: Path | None = None) -> Path:
    path = path or REPO_DIR / "docs" / "EVALUATION.md"
    L = ["# Draft strategy evaluation (retrospective mock drafts)", "",
         f"Generated {datetime.now(UTC).isoformat(timespec='seconds')}. Target season {exp.target}; 12-team snake, 13 rounds, "
         "H2H each category with ties worth half, 10 starters, four-center cap. Every strategy drafts from the same seat with "
         "the same opponent randomness; the other 11 teams draft by value order with positional need and noise.", "",
         "**Read this first.** " + " ".join(exp.notes), "",
         "Scoring: the completed roster's realized season totals (top 10 by minutes) against each of the 11 other teams in the same "
         "draft, categories won per matchup (0–9, ties half), its win rate (> 4.5 categories), and its rank in that league.", "",
         "## Strategies", "",
         "- `adp_bot`: the same policy the opponents use (value order + need + noise).",
         "- `naive_last_season`: best available by last season's per-game numbers (no projection model).",
         "- `static_value`: best available by projected season value (unweighted z-sum), no roster logic.",
         "- `static_need`: static value restricted to players who fill an open starting slot.",
         "- `fast`: the copilot's fast ranking (strategy-weighted value above replacement at the following pick, feasibility).",
         "- `refined`: the copilot's refined layer (draft rollouts + weekly matchup simulation; marginal categories won).", "",
         "## Results per strategy", "", "| strategy | drafts | categories won / matchup | matchup win rate | mean league rank (of 12) | top-3 finishes |",
         "|---|---|---|---|---|---|"]
    for s, v in summary["per_strategy"].items():
        L.append(f"| {s} | {v['n']} | {v['cats_won']:.2f} | {v['win_rate']:.1%} | {v['rank']:.1f} | {v['top3_share']:.0%} |")
    for ref, rows in summary["paired_vs"].items():
        L += ["", f"## Paired differences vs `{ref}` (same seat, same seed)", "",
              "| strategy | pairs | Δ categories won | ± SE | better / worse / equal | Δ rank |", "|---|---|---|---|---|---|"]
        for s, v in rows.items():
            L.append(f"| {s} | {v['n_pairs']} | {v['mean_diff_cats_won']:+.2f} | {v['se']:.2f} | {v['wins']} / {v['losses']} / {v['ties']} | {v['mean_diff_rank']:+.1f} |")
    L += ["", "A difference is meaningful when it is at least two standard errors from zero. Simulated and retrospective results describe "
          "this experiment's assumptions, not guaranteed draft outcomes.", "", f"Raw results: `docs/{path.with_suffix('.json').name}`."]
    path.write_text("\n".join(L) + "\n")
    (path.with_suffix(".json")).write_text(json.dumps({"target": exp.target, "notes": exp.notes, "results": exp.results,
                                                                      "summary": summary}, indent=1))
    return path
