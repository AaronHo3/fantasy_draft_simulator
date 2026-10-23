"""Application-wide singletons wired at startup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.persistence.store import SessionStore
from app.projections.registry import SnapshotRegistry
from app.recommend.jobs import JobManager
from app.season.live_status import read_live_status
from app.settings import Settings
from app.sources.espn_league import EspnLeague

LeagueFetcher = Callable[[int, int], tuple[EspnLeague, dict[str, Any]]]
PlayersFetcher = Callable[[int], pd.DataFrame]
BoxscoreFetcher = Callable[[int, int, int], dict[str, Any]]


def _default_fetch_league(league_id: int, season_id: int) -> tuple[EspnLeague, dict[str, Any]]:
    from datetime import UTC, datetime

    from app.sources.espn_league import fetch_league_raw, parse_league

    raw = fetch_league_raw(league_id, season_id)
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    return parse_league(raw.payload, league_id, season_id, fetched_at), raw.payload


def _default_fetch_boxscore(league_id: int, season_id: int, scoring_period_id: int) -> dict[str, Any]:
    from app.sources.espn_league import fetch_boxscore_raw

    return fetch_boxscore_raw(league_id, season_id, scoring_period_id)


def _default_fetch_players(season_id: int) -> pd.DataFrame:
    from app.sources.espn_public import fetch_players

    return fetch_players(season_id)


@dataclass
class AppContext:
    settings: Settings
    store: SessionStore
    registry: SnapshotRegistry
    jobs: JobManager
    espn_fetch_league: LeagueFetcher = _default_fetch_league
    espn_fetch_players: PlayersFetcher = _default_fetch_players
    espn_fetch_boxscore: BoxscoreFetcher = _default_fetch_boxscore
    leagues: dict[int, EspnLeague] = field(default_factory=dict)  # last parsed league per league id
    _schedule: pd.DataFrame | None = field(default=None, repr=False)
    _schedule_loaded: bool = False
    _live: dict[int, pd.DataFrame | None] = field(default_factory=dict, repr=False)

    def get_schedule(self) -> pd.DataFrame | None:
        """NBA game schedule from ``make refresh`` (None when not fetched yet)."""
        if not self._schedule_loaded:
            path = self.settings.schedule_path
            self._schedule = pd.read_parquet(path) if path.exists() else None
            self._schedule_loaded = True
        return self._schedule

    def team_schedule(self):
        """Per-team game days by week, built once from the schedule parquet (None when not fetched)."""
        from app.engine.schedule_model import build_team_schedule

        if not hasattr(self, "_team_schedule"):
            sched = self.get_schedule()
            self._team_schedule = build_team_schedule(sched) if sched is not None else None
        return self._team_schedule

    def live_status(self, league_id: int) -> pd.DataFrame | None:
        if league_id not in self._live:
            self._live[league_id] = read_live_status(self.settings.live_dir, league_id)
        return self._live[league_id]

    def invalidate_live_status(self, league_id: int) -> None:
        self._live.pop(league_id, None)


_ctx: AppContext | None = None


def build_context(settings: Settings) -> AppContext:
    settings.sessions_db.parent.mkdir(parents=True, exist_ok=True)
    store = SessionStore(settings.sessions_db)
    registry = SnapshotRegistry(settings.demo_dir, settings.snapshots_dir)
    registry.load_all()
    return AppContext(settings, store, registry, JobManager(settings.refine_workers))


def set_context(ctx: AppContext) -> None:
    global _ctx
    _ctx = ctx


def get_context() -> AppContext:
    assert _ctx is not None, "app context not initialised"
    return _ctx
