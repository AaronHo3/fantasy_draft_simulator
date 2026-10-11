"""Engine latency benchmark on the 600-player demo fixture (12 managers). Writes docs/BENCHMARKS.md.

Measures, on this machine: Layer A fast ranking (p50/p95) at several draft stages, pick-commit
latency through the SQLite store, and refinement rollouts achieved inside the default budget.
"""

from __future__ import annotations

import json
import platform
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.api import schemas as S
from app.demo.generate import generate_demo_snapshot
from app.draft.events import EventType
from app.engine.layer_a import RankingContext, rank_layer_a
from app.league.config import demo_league_config
from app.league.strategy import Strategy
from app.persistence.store import SessionStore
from app.recommend.refine import run_refinement
from app.recommend.service import fast_recommendation
from app.settings import REPO_DIR


def _pct(xs: list[float], q: float) -> float:
    return float(np.percentile(xs, q))


def run_benchmarks(out: Path | None = None, repeats: int = 30) -> int:
    snap = generate_demo_snapshot()
    league = demo_league_config()
    results: dict[str, object] = {
        "machine": f"{platform.platform()} / {platform.processor() or platform.machine()}",
        "python": platform.python_version(),
        "players": snap.n,
        "managers": league.n_managers,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    order = np.argsort(np.where(np.isfinite(snap.adp), snap.adp, 1e9))
    # Layer A at draft stages (0, 30, 78, 130 picks made)
    stage_rows = []
    for n_drafted in (0, 30, 78, 130):
        drafted = frozenset(snap.players[i].player_id for i in order[:n_drafted])
        mine = tuple(snap.players[order[k]].player_id for k in range(5, n_drafted, 12))
        ctx = RankingContext(snap, league, Strategy(), drafted, mine, 13 - len(mine), 11, 156 - n_drafted)
        rank_layer_a(ctx, n_drafted + 1)
        times = []
        for _ in range(repeats):
            t = time.perf_counter()
            rank_layer_a(ctx, n_drafted + 1)
            times.append((time.perf_counter() - t) * 1000)
        stage_rows.append(
            {"drafted": n_drafted, "p50_ms": round(_pct(times, 50), 1), "p95_ms": round(_pct(times, 95), 1)}
        )
    results["layer_a_engine"] = stage_rows
    # full fast recommendation response (engine + views + explanations) via the store
    with tempfile.TemporaryDirectory() as td:
        store = SessionStore(Path(td) / "b.sqlite")
        sid = store.create_session(league, snapshot_id=snap.snapshot_id)
        commit_times, fast_times = [], []
        for k in range(60):
            st = store.state(sid)
            cp = st.current_pick
            t = time.perf_counter()
            store.append(
                sid,
                EventType.pick_committed,
                {"player_id": snap.players[order[k]].player_id, "overall": cp.overall, "manager_id": cp.manager_id},
            )
            commit_times.append((time.perf_counter() - t) * 1000)
            if k % 6 == 5:
                st = store.state(sid)
                t = time.perf_counter()
                fast_recommendation(snap, st, S.FastRecommendRequest(limit=25), 1)
                fast_times.append((time.perf_counter() - t) * 1000)
        results["pick_commit_ms"] = {"p50": round(_pct(commit_times, 50), 2), "p95": round(_pct(commit_times, 95), 2)}
        results["fast_recommendation_ms"] = {
            "p50": round(_pct(fast_times, 50), 1),
            "p95": round(_pct(fast_times, 95), 1),
            "n": len(fast_times),
        }
        # refinement under the default budget at a mid-draft state (user on the clock at pick 66)
        st = store.state(sid)
        while st.current_pick.manager_id != league.user_manager_id:
            cp = st.current_pick
            store.append(
                sid,
                EventType.pick_committed,
                {
                    "player_id": snap.players[order[cp.overall - 1]].player_id,
                    "overall": cp.overall,
                    "manager_id": cp.manager_id,
                },
            )
            st = store.state(sid)
        ref_rows = []
        for budget in (1000, 1500, 3000):
            runs = []
            for seed in range(3):
                r = run_refinement(snap, st, S.RefineRequest(limit=8, budget_ms=budget), seed)
                runs.append(r)
            ref_rows.append(
                {
                    "budget_ms": budget,
                    "computed_ms_mean": round(statistics.mean(r.computed_ms for r in runs), 0),
                    "computed_ms_max": round(max(r.computed_ms for r in runs), 0),
                    "scenarios_mean": round(statistics.mean(r.scenarios for r in runs), 0),
                    "tier": runs[0].tier,
                }
            )
        results["refinement"] = ref_rows
        store.close()
    print(json.dumps(results, indent=1))
    target = out or (REPO_DIR / "docs" / "BENCHMARKS.md")
    target.write_text(_render(results))
    print(f"wrote {target}")
    return 0


def _render(r: dict) -> str:
    lines = [
        "# Benchmarks",
        "",
        f"Measured {r['timestamp']} on {r['machine']} (Python {r['python']}), {r['players']} synthetic players, "
        f"{r['managers']} managers. Produced by `make bench`; numbers below are from the last run, not targets.",
        "",
        "## Layer A engine (fast ranking over all available players)",
        "",
        "| picks made | p50 ms | p95 ms |",
        "|---|---|---|",
    ]
    for row in r["layer_a_engine"]:
        lines.append(f"| {row['drafted']} | {row['p50_ms']} | {row['p95_ms']} |")
    f = r["fast_recommendation_ms"]
    c = r["pick_commit_ms"]
    lines += [
        "",
        "## End-to-end service calls (engine + explanations + roster views, no HTTP)",
        "",
        f"- Fast recommendation (limit 25, 8 delta tables): p50 {f['p50']} ms, p95 {f['p95']} ms over {f['n']} calls.",
        f"- Pick commit through the SQLite event store (validate + replay + persist): p50 {c['p50']} ms, p95 {c['p95']} ms.",
        "",
        "## Refinement (Layers B/C) at the user's mid-draft pick, shortlist of 8",
        "",
        "| budget ms | mean computed ms | max computed ms | mean weekly scenarios | tier |",
        "|---|---|---|---|---|",
    ]
    for row in r["refinement"]:
        lines.append(
            f"| {row['budget_ms']} | {row['computed_ms_mean']} | {row['computed_ms_max']} | {row['scenarios_mean']} | {row['tier']} |"
        )
    lines += [
        "",
        "Targets from the brief: committed pick visible in ~100 ms (client-side optimistic), cached fast rankings "
        "< 250 ms p95, refined shortlist in ~1–2 s p95 under the default budget. See PROGRESS.md for the pass/fail reading.",
    ]
    return "\n".join(lines) + "\n"
