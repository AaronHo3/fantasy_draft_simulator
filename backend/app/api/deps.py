"""Application-wide singletons wired at startup."""

from __future__ import annotations

from dataclasses import dataclass

from app.persistence.store import SessionStore
from app.projections.registry import SnapshotRegistry
from app.recommend.jobs import JobManager
from app.settings import Settings


@dataclass
class AppContext:
    settings: Settings
    store: SessionStore
    registry: SnapshotRegistry
    jobs: JobManager


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
