from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.sources.base import (
    FetchError,
    RawResponse,
    SourceRun,
    raw_paths,
    read_parquet_if_exists,
    read_raw,
    read_raw_meta,
    sha256_hex,
    with_retries,
    write_parquet_atomic,
    write_raw,
)


def test_with_retries_returns_after_transient_failures():
    calls: list[int] = []
    delays: list[float] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("boom")
        return "ok"

    out = with_retries(flaky, attempts=3, base_delay=0.5, sleep=delays.append, rng=lambda: 0.0)
    assert out == "ok" and len(calls) == 3
    assert delays == [0.5, 1.0]  # exponential, jitter factor 1 + rng() with rng = 0


def test_with_retries_jitter_and_cap():
    delays: list[float] = []

    def always() -> None:
        raise TimeoutError("slow")

    with pytest.raises(FetchError) as exc:
        with_retries(always, attempts=4, base_delay=1.0, max_delay=2.0, sleep=delays.append, rng=lambda: 0.5)
    assert isinstance(exc.value.__cause__, TimeoutError)
    assert delays == [1.5, 3.0, 3.0]  # 1*1.5, min(2,2)*1.5, min(2,4)*1.5


def test_with_retries_exhausted_counts_attempts():
    calls: list[int] = []

    def always() -> None:
        calls.append(1)
        raise ValueError("bad")

    with pytest.raises(FetchError, match="3 attempts failed"):
        with_retries(always, attempts=3, sleep=lambda _: None)
    assert len(calls) == 3
    with pytest.raises(ValueError):
        with_retries(always, attempts=0)


def test_with_retries_does_not_retry_unlisted_exceptions():
    calls: list[int] = []

    def once() -> None:
        calls.append(1)
        raise KeyError("x")

    with pytest.raises(KeyError):
        with_retries(once, attempts=3, retry_on=(ValueError,), sleep=lambda _: None)
    assert len(calls) == 1


def test_source_run_to_dict_and_duration():
    run = SourceRun(
        "nba_api",
        "commonallplayers",
        "2026-27",
        "2026-10-09T10:00:00+00:00",
        "2026-10-09T10:00:02+00:00",
        "ok",
        rows=5,
        content_hash="abc",
    )
    d = run.to_dict()
    assert d["duration_s"] == 2.0 and d["status"] == "ok" and d["rows"] == 5 and d["error"] is None


def test_write_raw_and_meta_roundtrip(tmp_path: Path):
    payload = {"resultSets": [{"headers": ["A"], "rowSet": [[1]]}]}
    body = json.dumps(payload).encode()
    resp = RawResponse(payload, body, "https://x/y", {"season": "2025-26"})
    entry = write_raw(tmp_path, "nba_api", "commonallplayers", "2025-26", resp, fetched_at="2026-10-09T00:00:00+00:00")
    path, meta_path = raw_paths(tmp_path, "nba_api", "commonallplayers", "2025-26")
    assert entry.path == path and path.read_bytes() == body
    assert entry.sha256 == sha256_hex(body)
    meta = read_raw_meta(tmp_path, "nba_api", "commonallplayers", "2025-26")
    assert meta == {
        "source": "nba_api",
        "endpoint": "commonallplayers",
        "key": "2025-26",
        "fetched_at": "2026-10-09T00:00:00+00:00",
        "sha256": entry.sha256,
        "bytes": len(body),
        "url": "https://x/y",
        "params": {"season": "2025-26"},
    }
    assert read_raw(tmp_path, "nba_api", "commonallplayers", "2025-26") == payload
    assert read_raw(tmp_path, "nba_api", "commonallplayers", "missing") is None
    assert not list(path.parent.glob("*.tmp"))


def test_parquet_atomic_write_and_read(tmp_path: Path):
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", None]})
    path = tmp_path / "nba" / "normalized" / "t.parquet"
    write_parquet_atomic(frame, path)
    back = read_parquet_if_exists(path)
    assert back is not None and back["a"].tolist() == [1, 2] and pd.isna(back["b"].iloc[1])
    assert read_parquet_if_exists(tmp_path / "nope.parquet") is None
    assert not list(path.parent.glob("*.tmp"))
