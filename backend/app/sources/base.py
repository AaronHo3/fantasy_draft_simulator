"""Shared plumbing for data-source adapters: run records, bounded retries, raw/parquet caches.

Layout under ``data_dir`` (the repository ``data/`` directory):

    data/nba/raw/<source>/<endpoint>/<key>.json        verbatim response body
    data/nba/raw/<source>/<endpoint>/<key>.meta.json   fetched_at, sha256, url, params
    data/nba/normalized/<table>.parquet                normalized tables

All writes are atomic (temp file + ``os.replace``) and only happen after a fetch succeeded, so a
failed fetch can never overwrite an existing raw file or an existing normalized parquet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

log = logging.getLogger(__name__)

RunStatus = Literal["ok", "failed", "skipped"]
RAW_SUBDIR = ("nba", "raw")
NORMALIZED_SUBDIR = ("nba", "normalized")
DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 0.5
MAX_DELAY_S = 30.0


class FetchError(RuntimeError):
    """A fetch failed after all bounded retries."""


class SchemaError(ValueError):
    """A source response did not have the expected shape."""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def to_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@dataclass(frozen=True)
class SourceRun:
    """One fetch attempt of one endpoint/key, as recorded in ``source_runs.json``."""

    source: str
    endpoint: str
    key: str
    started_at: str
    finished_at: str
    status: RunStatus
    rows: int = 0
    error: str | None = None
    content_hash: str | None = None
    raw_path: str | None = None

    @property
    def duration_s(self) -> float:
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at)
        return max(0.0, (end - start).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "duration_s": round(self.duration_s, 3)}


@dataclass(frozen=True)
class RawResponse:
    """What a raw fetcher returns: the parsed payload plus the exact bytes and request identity."""

    payload: Any
    body: bytes
    url: str
    params: dict[str, Any]


@dataclass(frozen=True)
class RawCacheEntry:
    path: Path
    meta_path: Path
    sha256: str
    fetched_at: str


def with_retries(
    fn: Callable[[], Any],
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_S,
    *,
    max_delay: float = MAX_DELAY_S,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
) -> Any:
    """Call ``fn`` up to ``attempts`` times with exponential backoff and jitter.

    Delay before retry ``i`` (0-based) is ``min(max_delay, base_delay * 2**i) * (1 + jitter)``
    with ``jitter`` drawn from ``rng()`` in [0, 1). Raises :class:`FetchError` chained to the last
    exception once attempts are exhausted.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except retry_on as exc:
            last = exc
            if attempt + 1 >= attempts:
                break
            delay = min(max_delay, base_delay * (2**attempt)) * (1.0 + rng())
            log.warning("attempt %d/%d failed (%s); retrying in %.2fs", attempt + 1, attempts, exc, delay)
            sleep(delay)
    raise FetchError(f"{attempts} attempts failed; last error: {last!r}") from last


# --- raw cache -------------------------------------------------------------------------------


def raw_dir(data_dir: Path, source: str, endpoint: str) -> Path:
    return Path(data_dir).joinpath(*RAW_SUBDIR, source, endpoint)


def raw_paths(data_dir: Path, source: str, endpoint: str, key: str) -> tuple[Path, Path]:
    d = raw_dir(data_dir, source, endpoint)
    return d / f"{key}.json", d / f"{key}.meta.json"


def _atomic_write_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(body)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_raw(
    data_dir: Path,
    source: str,
    endpoint: str,
    key: str,
    response: RawResponse,
    fetched_at: str | None = None,
) -> RawCacheEntry:
    """Persist a successful response body and its metadata; both writes are atomic."""
    path, meta_path = raw_paths(data_dir, source, endpoint, key)
    digest = sha256_hex(response.body)
    at = fetched_at or utc_now_iso()
    meta = {
        "source": source,
        "endpoint": endpoint,
        "key": key,
        "fetched_at": at,
        "sha256": digest,
        "bytes": len(response.body),
        "url": response.url,
        "params": response.params,
    }
    _atomic_write_bytes(path, response.body)
    _atomic_write_bytes(meta_path, json.dumps(meta, indent=1, sort_keys=True).encode("utf-8"))
    return RawCacheEntry(path=path, meta_path=meta_path, sha256=digest, fetched_at=at)


def read_raw(data_dir: Path, source: str, endpoint: str, key: str) -> Any | None:
    """Parsed JSON of a cached raw response, or None when absent or unreadable."""
    path, _ = raw_paths(data_dir, source, endpoint, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        log.error("unreadable raw cache %s: %s", path, exc)
        return None


def read_raw_meta(data_dir: Path, source: str, endpoint: str, key: str) -> dict[str, Any] | None:
    _, meta_path = raw_paths(data_dir, source, endpoint, key)
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        log.error("unreadable raw meta %s: %s", meta_path, exc)
        return None
    return meta if isinstance(meta, dict) else None


# --- normalized tables -----------------------------------------------------------------------


def normalized_dir(data_dir: Path) -> Path:
    return Path(data_dir).joinpath(*NORMALIZED_SUBDIR)


def parquet_path(data_dir: Path, table: str) -> Path:
    return normalized_dir(data_dir) / f"{table}.parquet"


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def read_parquet_if_exists(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError) as exc:
        log.error("unreadable parquet %s: %s", path, exc)
        return None


def write_json_atomic(obj: Any, path: Path) -> Path:
    _atomic_write_bytes(path, json.dumps(obj, indent=1, sort_keys=True, default=str).encode("utf-8"))
    return path


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        log.error("unreadable json %s: %s", path, exc)
        return None
