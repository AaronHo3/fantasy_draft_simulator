"""Snapshot registry: the demo snapshot plus any built real snapshots under data/nba/snapshots."""

from __future__ import annotations

import logging
from pathlib import Path

from app.demo.generate import generate_demo_snapshot
from app.projections.snapshot import Snapshot, validate_snapshot

log = logging.getLogger(__name__)


class SnapshotRegistry:
    def __init__(self, demo_dir: Path, snapshots_dir: Path):
        self.demo_dir = demo_dir
        self.snapshots_dir = snapshots_dir
        self._snaps: dict[str, Snapshot] = {}
        self._errors: dict[str, str] = {}

    def load_all(self) -> None:
        demo = self._load_or_build_demo()
        self._snaps[demo.snapshot_id] = demo
        if self.snapshots_dir.exists():
            for d in sorted(self.snapshots_dir.iterdir()):
                if not (d / "meta.json").exists():
                    continue
                try:
                    s = Snapshot.load(d)
                    problems = validate_snapshot(s)
                    if problems:
                        self._errors[d.name] = "; ".join(problems)
                        log.warning("snapshot %s failed validation: %s", d.name, problems)
                        continue
                    self._snaps[s.snapshot_id] = s
                except Exception as e:  # noqa: BLE001 - a bad snapshot must not break startup
                    self._errors[d.name] = str(e)
                    log.warning("could not load snapshot %s: %s", d.name, e)

    def _load_or_build_demo(self) -> Snapshot:
        try:
            if (self.demo_dir / "meta.json").exists():
                return Snapshot.load(self.demo_dir)
        except Exception as e:  # noqa: BLE001
            log.warning("demo snapshot unreadable, regenerating: %s", e)
        s = generate_demo_snapshot()
        try:
            s.save(self.demo_dir)
        except OSError as e:
            log.warning("could not save demo snapshot: %s", e)
        return s

    def list(self) -> list[Snapshot]:
        real = sorted((s for s in self._snaps.values() if not s.is_demo), key=lambda s: s.created_at, reverse=True)
        demo = [s for s in self._snaps.values() if s.is_demo]
        return real + demo

    def get(self, snapshot_id: str) -> Snapshot:
        return self._snaps[snapshot_id]

    def has(self, snapshot_id: str) -> bool:
        return snapshot_id in self._snaps

    def default_id(self) -> str:
        return self.list()[0].snapshot_id

    def register(self, s: Snapshot) -> None:
        self._snaps[s.snapshot_id] = s

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)
