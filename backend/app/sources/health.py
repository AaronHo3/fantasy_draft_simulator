"""Health summary of the normalized data directory (what exists, how fresh, how complete)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from app.sources.base import SourceRun, normalized_dir, parquet_path, read_json_if_exists, utc_now_iso

TABLES: tuple[str, ...] = (
    "players",
    "season_totals",
    "game_logs",
    "espn_players",
    "schedule",
    "crosswalk",
)
HEALTH_FILE = "health.json"
SOURCE_RUNS_FILE = "source_runs.json"
UNRESOLVED_FILE = "unresolved.json"


def table_status(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Row counts and modification times of every normalized parquet (metadata only, cheap)."""
    out: dict[str, dict[str, Any]] = {}
    for name in TABLES:
        path = parquet_path(data_dir, name)
        entry: dict[str, Any] = {"path": str(path), "exists": path.exists(), "rows": 0, "modified_at": None}
        if path.exists():
            try:
                entry["rows"] = int(pq.read_metadata(path).num_rows)
            except (OSError, ValueError) as exc:  # pragma: no cover - corrupt file
                entry["error"] = f"{type(exc).__name__}: {exc}"
            mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            entry["modified_at"] = mtime.isoformat(timespec="seconds")
        out[name] = entry
    return out


def source_status(runs: list[SourceRun]) -> dict[str, dict[str, Any]]:
    """Per-source rollup: ok | partial | failed | skipped plus the latest successful fetch time."""
    out: dict[str, dict[str, Any]] = {}
    for source in sorted({r.source for r in runs}):
        mine = [r for r in runs if r.source == source]
        ok = [r for r in mine if r.status == "ok"]
        failed = [r for r in mine if r.status == "failed"]
        if ok and not failed:
            status = "ok"
        elif ok:
            status = "partial"
        elif failed:
            status = "failed"
        else:
            status = "skipped"
        out[source] = {
            "status": status,
            "runs": len(mine),
            "ok": len(ok),
            "failed": len(failed),
            "fetched_at": max((r.finished_at for r in ok), default=None),
            "errors": [{"endpoint": r.endpoint, "key": r.key, "error": r.error} for r in failed],
        }
    return out


def _count_true(frame: pd.DataFrame | None, mask) -> int:
    if frame is None or frame.empty:
        return 0
    return int(mask(frame).sum())


def coverage(
    players: pd.DataFrame | None,
    espn_players: pd.DataFrame | None,
    crosswalk: pd.DataFrame | None,
    schedule: pd.DataFrame | None,
    unresolved: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Player coverage counts the snapshot builder cares about."""
    linked = _count_true(crosswalk, lambda f: f["nba_id"].notna() & f["espn_id"].notna())
    return {
        "nba_players": 0 if players is None else int(len(players)),
        "espn_active_players": 0 if espn_players is None else int(len(espn_players)),
        "crosswalk_rows": 0 if crosswalk is None else int(len(crosswalk)),
        "linked_players": linked,
        "nba_only": _count_true(crosswalk, lambda f: f["match_method"] == "nba_only"),
        "espn_only": _count_true(crosswalk, lambda f: f["match_method"] == "espn_only"),
        "unresolved_identities": 0 if unresolved is None else len(unresolved),
        # NBA players with no ESPN record have no verified eligibility (never substituted).
        "missing_eligibility": _count_true(crosswalk, lambda f: f["match_method"] == "nba_only")
        + _count_true(espn_players, lambda f: f["eligible_positions_json"] == "[]"),
        "espn_projection_rows": _count_true(espn_players, lambda f: f["proj_gp"].notna()),
        "espn_prev_season_rows": _count_true(espn_players, lambda f: f["prev_gp"].notna()),
        "espn_adp_rows": _count_true(espn_players, lambda f: f["adp"].notna()),
        "schedule_games": 0 if schedule is None else int(len(schedule)),
    }


def build_health(
    data_dir: Path,
    runs: list[SourceRun],
    frames: dict[str, pd.DataFrame | None],
    unresolved: list[dict[str, Any]] | None,
    kept_previous: tuple[str, ...] = (),
) -> dict[str, Any]:
    ok_times = [r.finished_at for r in runs if r.status == "ok"]
    snapshot = max(ok_times)[:10] if ok_times else None
    return {
        "generated_at": utc_now_iso(),
        "snapshot_date": snapshot,
        "data_dir": str(Path(data_dir).resolve()),
        "sources": source_status(runs),
        "tables": table_status(data_dir),
        "kept_previous": list(kept_previous),
        "coverage": coverage(
            frames.get("players"),
            frames.get("espn_players"),
            frames.get("crosswalk"),
            frames.get("schedule"),
            unresolved,
        ),
    }


def health_report(data_dir: Path) -> dict[str, Any]:
    """Read ``health.json`` if present and refresh its table section from what is on disk."""
    nd = normalized_dir(data_dir)
    stored = read_json_if_exists(nd / HEALTH_FILE)
    report: dict[str, Any] = dict(stored) if isinstance(stored, dict) else {}
    report["tables"] = table_status(data_dir)
    report["checked_at"] = utc_now_iso()
    unresolved = read_json_if_exists(nd / UNRESOLVED_FILE)
    if isinstance(unresolved, list):
        report.setdefault("coverage", {})["unresolved_identities"] = len(unresolved)
    runs = read_json_if_exists(nd / SOURCE_RUNS_FILE)
    report["source_runs_recorded"] = len(runs) if isinstance(runs, list) else 0
    return json.loads(json.dumps(report, default=str))
