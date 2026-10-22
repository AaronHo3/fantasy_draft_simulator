"""Command line entry points: demo, openapi, export, import-session, health, refresh, build-snapshot, bench."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from app.api.deps import build_context
from app.settings import REPO_DIR, settings


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
    cols = [
        "target",
        "variant",
        "spearman_value",
        "top150_overlap",
        "top50_overlap",
        "value_mae",
        "mae_MIN",
        "mae_GP",
        "mae_PTS",
    ]
    print(df[cols].sort_values(["target", "spearman_value"], ascending=[True, False]).to_string(index=False))
    print("wrote", write_report(df))
    return 0


def cmd_evaluate(ns: argparse.Namespace) -> int:
    from app.eval.mock_draft import run_experiment, summarize, write_report

    strategies = ns.strategies or ["adp_bot", "naive_last_season", "static_value", "static_need", "fast", "refined"]
    exp = run_experiment(
        settings.data_dir,
        seats=ns.seats,
        seeds=list(range(ns.seeds)),
        strategies=strategies,
        refined_seats=ns.refined_seats or None,
        budget_ms=ns.budget_ms,
        refined_seeds=ns.refined_seeds,
        user_model=ns.user_model,
        target=ns.target,
    )
    summary = summarize(exp)
    path = write_report(exp, summary, Path(ns.out) if ns.out else None)
    print(json.dumps(summary, indent=1))
    print(f"wrote {path}")
    return 0


def cmd_season(ns: argparse.Namespace) -> int:
    """Weekly standings: from ESPN when the session is linked, else from live NBA game logs."""
    from app.season.tracker import fetch_logs, standings_table, weekly_lines

    ctx = build_context(settings)
    state = ctx.store.state(ns.session_id)
    meta = ctx.store.session_meta(ns.session_id)
    if state.league.espn_league_id is not None and not ns.nba_logs:
        return _print_espn_week(ctx, ns.session_id, int(ns.week) if ns.week and ns.week.isdigit() else None)
    reg = ctx.registry
    snap = reg.get(meta["snapshot_id"]) if meta and reg.has(meta["snapshot_id"]) else reg.get(reg.default_id())
    logs = fetch_logs(state.league.season, ns.season_type)
    nba_ids = {
        p.nba_id: r.manager_id
        for r in state.picks.values()
        for p in [snap.players[snap.index[r.player_id]]]
        if p.nba_id
    }
    lines = weekly_lines(logs, nba_ids)
    if lines.empty:
        print(f"No {ns.season_type} games yet for {state.league.season}.")
        return 0
    weeks = sorted(lines["week"].unique())
    week = ns.week or weeks[-1]
    df, grid = standings_table(state, snap, lines, week)
    print(f"{ns.season_type} week of {week} (weeks available: {', '.join(weeks)})")
    print(df.to_string(index=False))
    if ns.out:
        with pd.ExcelWriter(ns.out, engine="openpyxl") as w:
            df.to_excel(w, sheet_name=f"week {week}", index=False)
            grid.to_excel(w, sheet_name="head-to-head")
            lines[lines["week"] == week].merge(
                pd.DataFrame(
                    {"nba_id": list(nba_ids), "team": [state.league.manager(m).name for m in nba_ids.values()]}
                ),
                on="nba_id",
            ).to_excel(w, sheet_name="player lines", index=False)
        print("wrote", ns.out)
    return 0


def cmd_espn_link(ns: argparse.Namespace) -> int:
    """Preview (and with --apply, store) the mapping between session managers and ESPN teams."""
    from app.season import service as season
    from app.season.service import SeasonError

    ctx = build_context(settings)
    overrides = {}
    for item in ns.map or []:
        mid, _, tid = item.partition("=")
        overrides[mid] = int(tid)
    try:
        preview = season.link_preview(ctx, ns.session_id, ns.league_id, overrides)
        print(f"ESPN league {preview.league_id}: {preview.league_name}")
        for m in preview.mapping:
            print(
                f"  {m.manager_id:>4}  {m.manager_name:<24} -> team {m.team_id:>2}  {m.team_name:<28} ({m.owner_name}; overlap {m.overlap:.0%}, {m.confidence})"
            )
        for w in preview.settings_warnings + preview.warnings:
            print("  !", w)
        if preview.unmatched_managers or preview.unmatched_teams:
            print("  unmatched managers:", preview.unmatched_managers, "unmatched teams:", preview.unmatched_teams)
        if not ns.apply:
            print("preview only; rerun with --apply to store the link")
            return 0
        season.link_apply(ctx, ns.session_id, ns.league_id, {m.manager_id: m.team_id for m in preview.mapping})
        print("linked")
    except SeasonError as e:
        print(f"error ({e.code}): {e.message}")
        return 1
    return 0


def cmd_espn_sync(ns: argparse.Namespace) -> int:
    from app.season import service as season
    from app.season.service import SeasonError

    ctx = build_context(settings)
    try:
        res = season.run_sync(ctx, ns.session_id, None)
    except SeasonError as e:
        print(f"error ({e.code}): {e.message}")
        return 1
    print(f"{res.summary} (fetched {res.fetched_at})")
    names = {m.id: m.name for m in res.state.league.managers}
    for c in res.changes:
        print(f"  {names.get(c.manager_id, c.manager_id)}: +{c.added} -{c.dropped}")
    for w in res.warnings:
        print("  !", w)
    return 0


def _print_espn_week(ctx, session_id: str, period: int | None) -> int:
    from app.season import service as season

    ov = season.overview(ctx, session_id, None, period)
    print(f"{ov.league_name}: matchup period {ov.current_period} (synced {ov.synced_at})")
    names = ov.manager_names
    for m in ov.matchups:
        if m.away_manager_id is None or m.odds is None:
            print(f"  {names[m.home_manager_id]}: bye")
            continue
        o = m.odds
        print(
            f"  {names[m.home_manager_id]} vs {names[m.away_manager_id]}: {o.expected_a:.2f} - {o.expected_b:.2f} cats, "
            f"P(home win) {o.p_win_a:.0%}, tie {o.p_tie:.0%}, games {o.games_a}/{o.games_b}"
        )
    res = season.results(ctx, session_id, ov.current_period, None)
    print("ESPN results so far:")
    for r in res.results:
        if r.away is None:
            continue
        print(f"  {names[r.home.manager_id]} {r.home.cats_won:.1f} - {r.away.cats_won:.1f} {names[r.away.manager_id]}")
    print("power rankings:")
    for p in ov.power:
        arrow = ov.movement.get(p.manager_id, 0)
        print(f"  {p.rank:>2}. {p.name:<24} {p.expected_cats:.2f} {'+' if arrow > 0 else ''}{arrow if arrow else ''}")
    return 0


def cmd_performance(ns: argparse.Namespace) -> int:
    """Actual vs projected lines for the user's roster this period (appends the CSV tracker) and the hottest free agents."""
    from app.season.live_status import status_overlay
    from app.season.performance import append_tracker, free_agent_hot_starts, performance_table
    from app.season.tracker import fetch_logs
    from app.season.weeks import current_period, period_window

    ctx = build_context(settings)
    state = ctx.store.state(ns.session_id)
    meta = ctx.store.session_meta(ns.session_id)
    snap = (
        ctx.registry.get(meta["snapshot_id"])
        if meta and ctx.registry.has(meta["snapshot_id"])
        else ctx.registry.get(ctx.registry.default_id())
    )
    from datetime import UTC, datetime, timedelta

    today = (datetime.now(UTC) - timedelta(hours=6)).date()
    period = ns.period or current_period(state.league.season, today)
    window = period_window(state.league.season, period)
    logs = fetch_logs(state.league.season, "Regular Season")
    uid = ns.manager or state.league.user_manager_id
    table = performance_table(snap, state, logs, period, uid, window)
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"performance_{ns.session_id}.csv"
    history = append_tracker(csv_path, table)
    status = status_overlay(snap, ctx.live_status(state.league.espn_league_id) if state.league.espn_league_id else None)
    hot = free_agent_hot_starts(snap, state, logs, status, window, limit=ns.limit)
    xlsx = out_dir / f"performance_{ns.session_id}.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        table.to_excel(w, sheet_name=f"week {period} roster", index=False)
        hot.to_excel(w, sheet_name=f"week {period} free agents", index=False)
        history.to_excel(w, sheet_name="tracker (all weeks)", index=False)
        piv = history.pivot_table(index="player", columns="period", values="value_delta", aggfunc="first")
        piv.to_excel(w, sheet_name="value delta by week")
    print(f"period {period} ({window[0]}..{window[1]}), {len(logs)} game logs; wrote {csv_path} and {xlsx}")
    show = [
        "player",
        "games",
        "min_actual",
        "min_proj",
        "pts_actual",
        "pts_proj",
        "reb_actual",
        "reb_proj",
        "ast_actual",
        "ast_proj",
        "value_actual",
        "value_proj",
        "value_delta",
    ]
    print(table[show].sort_values("value_delta", ascending=False).round(2).to_string(index=False))
    if not hot.empty:
        print("\nhottest free agents (actual per game so far vs projection):")
        print(
            hot[
                [
                    "player",
                    "team",
                    "pos",
                    "status",
                    "owned_pct",
                    "games",
                    "min_actual",
                    "min_proj",
                    "pts_actual",
                    "reb_actual",
                    "ast_actual",
                    "stl_actual",
                    "blk_actual",
                    "fg3m_actual",
                    "value_actual",
                    "value_proj",
                ]
            ]
            .round(2)
            .to_string(index=False)
        )
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
    ev.add_argument(
        "--user-model",
        help="alt_model drafts with this model spec, e.g. ridge, ens:rich, ens:rich:flat (opponents use the baseline)",
    )
    ev.add_argument("--target", default="2025-26")
    ev.set_defaults(fn=cmd_evaluate)
    se = sub.add_parser("season")
    se.add_argument("session_id")
    se.add_argument("--week", help="matchup period number when linked to ESPN; ISO Monday date for NBA logs")
    se.add_argument("--nba-logs", action="store_true", help="use nba_api game logs even when linked to ESPN")
    se.add_argument("--season-type", default="Regular Season", choices=["Regular Season", "Pre Season", "Playoffs"])
    se.add_argument("--out", help="write an .xlsx")
    se.set_defaults(fn=cmd_season)
    el = sub.add_parser("espn-link")
    el.add_argument("session_id")
    el.add_argument("league_id", type=int)
    el.add_argument("--map", nargs="*", help="manual overrides, e.g. m10=7")
    el.add_argument("--apply", action="store_true")
    el.set_defaults(fn=cmd_espn_link)
    es = sub.add_parser("espn-sync")
    es.add_argument("session_id")
    es.set_defaults(fn=cmd_espn_sync)
    pf = sub.add_parser("performance")
    pf.add_argument("session_id")
    pf.add_argument("--period", type=int)
    pf.add_argument("--manager")
    pf.add_argument("--limit", type=int, default=30)
    pf.add_argument("--out-dir", default=str(REPO_DIR / "exports"))
    pf.set_defaults(fn=cmd_performance)
    bn = sub.add_parser("bench")
    bn.add_argument("--out")
    bn.set_defaults(fn=cmd_bench)
    ns = p.parse_args(argv)
    return ns.fn(ns)


if __name__ == "__main__":
    sys.exit(main())
