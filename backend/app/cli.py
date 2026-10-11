"""Command line entry points: demo, openapi, export, import-session, health, refresh, build-snapshot, bench."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.settings import settings


def cmd_demo(_: argparse.Namespace) -> int:
    from app.api.deps import build_context
    from app.league.config import demo_league_config

    ctx = build_context(settings)
    demo = next(s for s in ctx.registry.list() if s.is_demo)
    sid = ctx.store.create_session(demo_league_config(), snapshot_id=demo.snapshot_id, name="Demo draft (synthetic)")
    print(
        json.dumps(
            {
                "session_id": sid,
                "snapshot_id": demo.snapshot_id,
                "players": demo.n,
                "label": demo.label,
                "url": f"http://127.0.0.1:5173/?session={sid}",
            },
            indent=1,
        )
    )
    ctx.store.close()
    return 0


def cmd_openapi(_: argparse.Namespace) -> int:
    from app.main import create_app

    print(json.dumps(create_app().openapi(), indent=1))
    return 0


def cmd_export(ns: argparse.Namespace) -> int:
    from app.persistence.store import SessionStore

    store = SessionStore(settings.sessions_db)
    data = store.export_session(ns.session_id)
    out = Path(ns.out) if ns.out else Path(f"session-{ns.session_id}.json")
    out.write_text(json.dumps(data, indent=1))
    print(f"exported {len(data['events'])} events to {out}")
    return 0


def cmd_import(ns: argparse.Namespace) -> int:
    from app.persistence.store import SessionStore

    store = SessionStore(settings.sessions_db)
    sid = store.import_session(json.loads(Path(ns.file).read_text()))
    print(json.dumps({"session_id": sid}))
    return 0


def cmd_health(_: argparse.Namespace) -> int:
    try:
        from app.sources.health import health_report

        print(json.dumps(health_report(settings.data_dir), indent=1, default=str))
    except ImportError as e:
        print(json.dumps({"status": "adapters unavailable", "detail": str(e)}))
    return 0


def cmd_refresh(ns: argparse.Namespace) -> int:
    from app.sources.refresh import refresh_all

    report = refresh_all(settings.data_dir, seasons=tuple(ns.seasons), current_season=ns.current)
    print(
        json.dumps(
            report if isinstance(report, dict) else getattr(report, "__dict__", str(report)), indent=1, default=str
        )
    )
    return 0


def cmd_build_snapshot(ns: argparse.Namespace) -> int:
    from app.projections.build import build_real_snapshot

    s = build_real_snapshot(settings.data_dir, season=ns.season)
    print(
        json.dumps(
            {"snapshot_id": s.snapshot_id, "players": s.n, "label": s.label, "health": s.health}, indent=1, default=str
        )
    )
    return 0


def cmd_validate(ns: argparse.Namespace) -> int:
    from app.projections.validate import validate

    r = validate(settings.data_dir, target=ns.target)
    for name, res in r["results"].items():
        print(
            f"{name:26s} PTS {res['PTS']['mae']:.2f} REB {res['REB']['mae']:.2f} AST {res['AST']['mae']:.2f} "
            f"STL {res['STL']['mae']:.3f} BLK {res['BLK']['mae']:.3f} 3PM {res['FG3M']['mae']:.2f} TOV {res['TOV']['mae']:.2f} "
            f"MIN {res['MIN']['mae']:.2f} GP {res['GP']['mae']:.1f} FG% {res['FG_PCT']['mae']:.4f} FT% {res['FT_PCT']['mae']:.4f}"
        )
    print("players:", r["n_players"], "-> docs/VALIDATION.md")
    return 0


def cmd_research(_: argparse.Namespace) -> int:
    from app.projections.research import evaluate, write_report

    df = evaluate(settings.data_dir)
    cols = ["target", "variant", "spearman_value", "top150_overlap", "top50_overlap", "value_mae", "mae_MIN", "mae_GP", "mae_PTS"]
    print(df[cols].sort_values(["target", "spearman_value"], ascending=[True, False]).to_string(index=False))
    print("wrote", write_report(df))
    return 0


def cmd_evaluate(ns: argparse.Namespace) -> int:
    from app.eval.mock_draft import run_experiment, summarize, write_report

    strategies = ns.strategies or ["adp_bot", "naive_last_season", "static_value", "static_need", "fast", "refined"]
    exp = run_experiment(settings.data_dir, seats=ns.seats, seeds=list(range(ns.seeds)), strategies=strategies,
                         refined_seats=ns.refined_seats or None, budget_ms=ns.budget_ms, refined_seeds=ns.refined_seeds,
                         user_model=ns.user_model, target=ns.target)
    summary = summarize(exp)
    path = write_report(exp, summary, Path(ns.out) if ns.out else None)
    print(json.dumps(summary, indent=1))
    print(f"wrote {path}")
    return 0


def cmd_bench(ns: argparse.Namespace) -> int:
    from app.bench import run_benchmarks

    return run_benchmarks(Path(ns.out) if ns.out else None)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="copilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    sub.add_parser("openapi").set_defaults(fn=cmd_openapi)
    e = sub.add_parser("export")
    e.add_argument("session_id")
    e.add_argument("--out")
    e.set_defaults(fn=cmd_export)
    i = sub.add_parser("import-session")
    i.add_argument("file")
    i.set_defaults(fn=cmd_import)
    sub.add_parser("health").set_defaults(fn=cmd_health)
    r = sub.add_parser("refresh")
    r.add_argument("--seasons", nargs="*", default=["2023-24", "2024-25", "2025-26"])
    r.add_argument("--current", default="2026-27")
    r.set_defaults(fn=cmd_refresh)
    b = sub.add_parser("build-snapshot")
    b.add_argument("--season", default="2026-27")
    b.set_defaults(fn=cmd_build_snapshot)
    v = sub.add_parser("validate")
    v.add_argument("--target", default="2025-26")
    v.set_defaults(fn=cmd_validate)
    sub.add_parser("research").set_defaults(fn=cmd_research)
    ev = sub.add_parser("evaluate-draft")
    ev.add_argument("--seats", nargs="*", type=int, default=list(range(1, 13)))
    ev.add_argument("--seeds", type=int, default=4)
    ev.add_argument("--strategies", nargs="*")
    ev.add_argument("--refined-seats", nargs="*", type=int, default=[1, 4, 6, 9, 12])
    ev.add_argument("--budget-ms", type=int, default=2000)
    ev.add_argument("--refined-seeds", type=int, default=4)
    ev.add_argument("--out")
    ev.add_argument("--user-model", help="alt_model drafts with this model spec, e.g. ridge, ens:rich, ens:rich:flat (opponents use the baseline)")
    ev.add_argument("--target", default="2025-26")
    ev.set_defaults(fn=cmd_evaluate)
    bn = sub.add_parser("bench")
    bn.add_argument("--out")
    bn.set_defaults(fn=cmd_bench)
    ns = p.parse_args(argv)
    return ns.fn(ns)


if __name__ == "__main__":
    sys.exit(main())
