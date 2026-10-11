"""Orchestrate a full refresh of league-wide tables into ``data/nba``.

Requests per refresh (defaults): nba_api 1 players + 3 season totals + 3x2 game logs = 10;
ESPN 2 (players, schedule). One failing fetch never aborts the others, never overwrites an
existing raw file, and never replaces an existing normalized parquet with a less complete one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from app.identity.crosswalk import build_crosswalk
from app.league.config import espn_season_id
from app.sources import espn_public, nba_stats
from app.sources.base import (
    RawResponse,
    SourceRun,
    normalized_dir,
    parquet_path,
    read_json_if_exists,
    read_parquet_if_exists,
    read_raw,
    read_raw_meta,
    utc_now_iso,
    write_json_atomic,
    write_parquet_atomic,
    write_raw,
)
from app.sources.health import HEALTH_FILE, SOURCE_RUNS_FILE, UNRESOLVED_FILE, build_health

log = logging.getLogger(__name__)

KNOWN_SOURCES: tuple[str, ...] = ("nba_api", "espn_public")
DEFAULT_SEASONS: tuple[str, ...] = ("2023-24", "2024-25", "2025-26")
DEFAULT_CURRENT_SEASON = "2026-27"


@dataclass(frozen=True)
class RefreshReport:
    started_at: str
    finished_at: str
    runs: tuple[SourceRun, ...]
    tables: dict[str, int]
    kept_previous: tuple[str, ...]
    unresolved_count: int
    health: dict[str, Any] = field(default_factory=dict)

    @property
    def failed_runs(self) -> tuple[SourceRun, ...]:
        return tuple(r for r in self.runs if r.status == "failed")

    def __str__(self) -> str:
        ok = sum(1 for r in self.runs if r.status == "ok")
        tables = ", ".join(f"{k}={v}" for k, v in self.tables.items())
        lines = [
            f"refresh {self.started_at} -> {self.finished_at}: {ok}/{len(self.runs)} fetches ok",
            f"tables written: {tables or 'none'}",
            f"kept previous: {', '.join(self.kept_previous) or 'none'}",
            f"unresolved identities: {self.unresolved_count}",
        ]
        lines += [f"FAILED {r.source}/{r.endpoint}/{r.key}: {r.error}" for r in self.failed_runs]
        return "\n".join(lines)


@dataclass(frozen=True)
class _Part:
    """Outcome of one fetch: its run record and the normalized frame (fresh or from raw cache)."""

    run: SourceRun
    frame: pd.DataFrame | None
    from_cache: bool = False


def _fetch_part(
    data_dir: Path,
    source: str,
    endpoint: str,
    key: str,
    fetch_raw: Callable[[], RawResponse],
    normalize: Callable[[Any, str], pd.DataFrame],
) -> _Part:
    started = utc_now_iso()
    try:
        raw = fetch_raw()
        entry = write_raw(data_dir, source, endpoint, key, raw)
        frame = normalize(raw.payload, entry.fetched_at)
    except Exception as exc:  # noqa: BLE001 - one failing source must not abort the others
        log.exception("fetch failed: %s/%s/%s", source, endpoint, key)
        error = f"{type(exc).__name__}: {exc}"
        run = SourceRun(source, endpoint, key, started, utc_now_iso(), "failed", 0, error)
        return _Part(run, _normalize_cached(data_dir, source, endpoint, key, normalize), True)
    run = SourceRun(
        source, endpoint, key, started, utc_now_iso(), "ok", int(len(frame)), None, entry.sha256, str(entry.path)
    )
    return _Part(run, frame)


def _normalize_cached(
    data_dir: Path, source: str, endpoint: str, key: str, normalize: Callable[[Any, str], pd.DataFrame]
) -> pd.DataFrame | None:
    cached = read_raw(data_dir, source, endpoint, key)
    if cached is None:
        return None
    meta = read_raw_meta(data_dir, source, endpoint, key) or {}
    try:
        frame = normalize(cached, str(meta.get("fetched_at") or "cached"))
    except Exception:  # noqa: BLE001
        log.exception("cached raw %s/%s/%s is not normalizable", source, endpoint, key)
        return None
    log.warning("using cached raw response for %s/%s/%s", source, endpoint, key)
    return frame


def _assemble(parts: Sequence[_Part]) -> tuple[pd.DataFrame | None, bool]:
    """Concatenate part frames; ``complete`` means every part produced a frame (fresh or cached)."""
    frames = [p.frame for p in parts if p.frame is not None]
    complete = len(frames) == len(parts) and bool(parts)
    if not frames:
        return None, False
    return pd.concat(frames, ignore_index=True), complete


def _write_table(
    data_dir: Path, name: str, frame: pd.DataFrame | None, complete: bool, tables: dict[str, int], kept: list[str]
) -> pd.DataFrame | None:
    """Write when complete, or when partial but nothing older exists; otherwise keep the old file."""
    path = parquet_path(data_dir, name)
    if frame is not None and (complete or not path.exists()):
        write_parquet_atomic(frame, path)
        tables[name] = int(len(frame))
        return frame
    previous = read_parquet_if_exists(path)
    if previous is not None:
        kept.append(name)
        log.warning("%s: keeping previous parquet (%d rows)", name, len(previous))
    return previous


def _nba_parts(
    data_dir: Path, seasons: Sequence[str], current_season: str, include_playoffs: bool
) -> dict[str, list[_Part]]:
    src = nba_stats.SOURCE
    players = [
        _fetch_part(
            data_dir,
            src,
            nba_stats.ENDPOINT_PLAYERS,
            current_season,
            lambda: nba_stats.fetch_players_raw(current_season),
            lambda payload, at: nba_stats.normalize_players(payload, current_season, at),
        )
    ]
    totals = [
        _fetch_part(
            data_dir,
            src,
            nba_stats.ENDPOINT_SEASON_TOTALS,
            f"{s}_regular_season",
            lambda s=s: nba_stats.fetch_season_totals_raw(s, "Regular Season"),
            lambda payload, at, s=s: nba_stats.normalize_season_totals(payload, s, "Regular Season", at),
        )
        for s in seasons
    ]
    types = nba_stats.SEASON_TYPES if include_playoffs else nba_stats.SEASON_TYPES[:1]
    logs = [
        _fetch_part(
            data_dir,
            src,
            nba_stats.ENDPOINT_GAME_LOGS,
            f"{s}_{nba_stats.season_type_slug(st)}",
            lambda s=s, st=st: nba_stats.fetch_game_logs_raw(s, st),
            lambda payload, at, s=s, st=st: nba_stats.normalize_game_logs(payload, s, st, at),
        )
        for s in seasons
        for st in types
    ]
    return {"players": players, "season_totals": totals, "game_logs": logs}


def _espn_parts(data_dir: Path, season_id: int) -> dict[str, list[_Part]]:
    src = espn_public.SOURCE
    players = [
        _fetch_part(
            data_dir,
            src,
            espn_public.ENDPOINT_PLAYERS,
            str(season_id),
            lambda: espn_public.fetch_players_raw(season_id),
            lambda payload, at: espn_public.parse_players(payload, season_id, at),
        )
    ]
    schedule = [
        _fetch_part(
            data_dir,
            src,
            espn_public.ENDPOINT_SCHEDULE,
            str(season_id),
            lambda: espn_public.fetch_schedule_raw(season_id),
            lambda payload, at: espn_public.parse_schedule(payload, season_id, at),
        )
    ]
    return {"espn_players": players, "schedule": schedule}


def _crosswalk_step(
    data_dir: Path, players: pd.DataFrame | None, espn: pd.DataFrame | None, tables: dict[str, int]
) -> tuple[SourceRun, pd.DataFrame | None, list[dict]]:
    started = utc_now_iso()
    if players is None or espn is None:
        missing = [n for n, f in (("players", players), ("espn_players", espn)) if f is None]
        run = SourceRun(
            "identity", "crosswalk", "all", started, utc_now_iso(), "skipped", 0, f"missing inputs: {missing}"
        )
        return run, read_parquet_if_exists(parquet_path(data_dir, "crosswalk")), []
    try:
        frame, unresolved = build_crosswalk(players, espn)
        write_parquet_atomic(frame, parquet_path(data_dir, "crosswalk"))
        write_json_atomic(unresolved, normalized_dir(data_dir) / UNRESOLVED_FILE)
    except Exception as exc:  # noqa: BLE001
        log.exception("crosswalk failed")
        run = SourceRun(
            "identity", "crosswalk", "all", started, utc_now_iso(), "failed", 0, f"{type(exc).__name__}: {exc}"
        )
        return run, read_parquet_if_exists(parquet_path(data_dir, "crosswalk")), []
    tables["crosswalk"] = int(len(frame))
    run = SourceRun("identity", "crosswalk", "all", started, utc_now_iso(), "ok", int(len(frame)))
    return run, frame, unresolved


def _append_runs(data_dir: Path, runs: Sequence[SourceRun]) -> None:
    path = normalized_dir(data_dir) / SOURCE_RUNS_FILE
    history = read_json_if_exists(path)
    history = list(history) if isinstance(history, list) else []
    write_json_atomic(history + [r.to_dict() for r in runs], path)


def refresh_all(
    data_dir: Path,
    seasons: Sequence[str] = DEFAULT_SEASONS,
    current_season: str = DEFAULT_CURRENT_SEASON,
    include_playoffs: bool = True,
    sources: Sequence[str] = KNOWN_SOURCES,
) -> RefreshReport:
    """Fetch every league-wide table, normalize, and persist under ``data_dir/nba``."""
    unknown = [s for s in sources if s not in KNOWN_SOURCES]
    if unknown:
        raise ValueError(f"unknown sources {unknown}; known: {KNOWN_SOURCES}")
    for s in (*seasons, current_season):
        espn_season_id(s)  # validates the "YYYY-YY" form
    data_dir = Path(data_dir)
    normalized_dir(data_dir).mkdir(parents=True, exist_ok=True)
    started = utc_now_iso()

    parts: dict[str, list[_Part]] = {}
    if "nba_api" in sources:
        parts.update(_nba_parts(data_dir, seasons, current_season, include_playoffs))
    if "espn_public" in sources:
        parts.update(_espn_parts(data_dir, espn_season_id(current_season)))

    runs: list[SourceRun] = [p.run for group in parts.values() for p in group]
    tables: dict[str, int] = {}
    kept: list[str] = []
    frames: dict[str, pd.DataFrame | None] = {}
    for name in ("players", "season_totals", "game_logs", "espn_players", "schedule"):
        if name in parts:
            frame, complete = _assemble(parts[name])
        else:
            frame, complete = None, False
        frames[name] = _write_table(data_dir, name, frame, complete, tables, kept)

    xw_run, frames["crosswalk"], unresolved = _crosswalk_step(
        data_dir, frames.get("players"), frames.get("espn_players"), tables
    )
    runs.append(xw_run)
    if xw_run.status != "ok":
        stored = read_json_if_exists(normalized_dir(data_dir) / UNRESOLVED_FILE)
        unresolved = list(stored) if isinstance(stored, list) else []

    _append_runs(data_dir, runs)
    health = build_health(data_dir, runs, frames, unresolved, tuple(kept))
    write_json_atomic(health, normalized_dir(data_dir) / HEALTH_FILE)
    return RefreshReport(started, utc_now_iso(), tuple(runs), tables, tuple(kept), len(unresolved), health)
