"""Bounded background jobs for refinement (Layer B/C). Never blocks the request loop."""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.draft.events import now_iso


@dataclass
class Job:
    id: str
    ids: dict[str, Any]
    status: str = "queued"  # queued | running | done | failed | cancelled
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    elapsed_ms: float | None = None


class JobManager:
    def __init__(self, workers: int = 2, max_jobs: int = 200):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="refine")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._max = max_jobs

    def submit(self, fn: Callable[[], Any], ids: dict[str, Any]) -> Job:
        job = Job(uuid.uuid4().hex[:10], ids)
        with self._lock:
            if len(self._jobs) >= self._max:
                for k in list(self._jobs)[: self._max // 2]:
                    if self._jobs[k].status in ("done", "failed", "cancelled"):
                        del self._jobs[k]
            self._jobs[job.id] = job

        def run() -> None:
            import time

            t0 = time.perf_counter()
            job.status = "running"
            try:
                job.result = fn()
                job.status = "done"
            except Exception as e:  # noqa: BLE001 - surfaced to the client
                job.error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
                job.status = "failed"
            finally:
                job.finished_at = now_iso()
                job.elapsed_ms = (time.perf_counter() - t0) * 1000

        self._pool.submit(run)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
