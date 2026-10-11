from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.sources import espn_public, nba_stats
from app.sources.base import FetchError, parquet_path, raw_paths, read_raw_meta, sha256_hex
from app.sources.health import health_report
from app.sources.refresh import refresh_all
from tests.sources.conftest import ESPN_FIXTURES, NBA_FIXTURES, raw_from

ALL_TABLES = ("players", "season_totals", "game_logs", "espn_players", "schedule", "crosswalk")


@pytest.fixture
def fake_sources(monkeypatch):
    """Route every raw fetcher at recorded fixtures and count calls."""
    calls: list[tuple[str, str]] = []

    def players_raw(season):
        calls.append(("nba_players", season))
        return raw_from(NBA_FIXTURES / "commonallplayers_2026-27.json")

    def totals_raw(season, season_type="Regular Season"):
        calls.append(("nba_totals", f"{season}/{season_type}"))
        return raw_from(NBA_FIXTURES / "leaguedashplayerstats_2025-26.json")

    def logs_raw(season, season_type="Regular Season"):
        calls.append(("nba_logs", f"{season}/{season_type}"))
        return raw_from(NBA_FIXTURES / "playergamelogs_2025-26_regular_season.json")

    def espn_players_raw(season_id, client=None):
        calls.append(("espn_players", str(season_id)))
        return raw_from(ESPN_FIXTURES / "players_2027.json")

    def espn_schedule_raw(season_id, client=None):
        calls.append(("espn_schedule", str(season_id)))
        return raw_from(ESPN_FIXTURES / "schedule_2027.json")

    monkeypatch.setattr(nba_stats, "fetch_players_raw", players_raw)
    monkeypatch.setattr(nba_stats, "fetch_season_totals_raw", totals_raw)
    monkeypatch.setattr(nba_stats, "fetch_game_logs_raw", logs_raw)
    monkeypatch.setattr(espn_public, "fetch_players_raw", espn_players_raw)
    monkeypatch.setattr(espn_public, "fetch_schedule_raw", espn_schedule_raw)
    return calls


def _nd(data_dir: Path) -> Path:
    return data_dir / "nba" / "normalized"


def test_refresh_all_writes_every_table_with_about_twelve_requests(tmp_path, fake_sources):
    report = refresh_all(tmp_path)
    assert len(fake_sources) == 12  # 1 + 3 + 6 nba_api, 2 espn_public
    assert len(report.runs) == 13 and all(r.status == "ok" for r in report.runs)
    assert report.tables == {
        "players": 22,
        "season_totals": 66,
        "game_logs": 72,
        "espn_players": 22,
        "schedule": 6,
        "crosswalk": 23,
    }
    assert report.kept_previous == () and report.unresolved_count == 2
    for name in ALL_TABLES:
        assert parquet_path(tmp_path, name).exists(), name
    logs = pd.read_parquet(parquet_path(tmp_path, "game_logs"))
    assert set(logs["season_type"]) == {"Regular Season", "Playoffs"}
    assert set(logs["season"]) == {"2023-24", "2024-25", "2025-26"}
    raw, meta = raw_paths(tmp_path, "nba_api", "playergamelogs", "2025-26_playoffs")
    assert raw.exists() and meta.exists()
    assert (_nd(tmp_path) / "unresolved.json").exists()
    runs = json.loads((_nd(tmp_path) / "source_runs.json").read_text())
    assert len(runs) == 13 and {r["status"] for r in runs} == {"ok"}
    health = json.loads((_nd(tmp_path) / "health.json").read_text())
    assert health["sources"]["nba_api"]["status"] == "ok"
    assert health["sources"]["espn_public"]["status"] == "ok"
    assert health["coverage"]["linked_players"] == 21 and health["coverage"]["nba_only"] == 1
    assert health["coverage"]["unresolved_identities"] == 2
    assert health["coverage"]["missing_eligibility"] == 1  # one NBA player without ESPN record
    assert health["coverage"]["espn_projection_rows"] == 21 and health["snapshot_date"]
    assert "requests" not in str(report) and "13/13 fetches ok" in str(report)


def test_refresh_subset_of_sources_and_history_append(tmp_path, fake_sources):
    r1 = refresh_all(tmp_path, seasons=("2025-26",), include_playoffs=False, sources=("nba_api",))
    assert [c[0] for c in fake_sources] == ["nba_players", "nba_totals", "nba_logs"]
    assert set(r1.tables) == {"players", "season_totals", "game_logs"}
    skipped = [r for r in r1.runs if r.status == "skipped"]
    assert len(skipped) == 1 and skipped[0].endpoint == "crosswalk"
    assert not parquet_path(tmp_path, "espn_players").exists()
    refresh_all(tmp_path, seasons=("2025-26",), include_playoffs=False, sources=("espn_public",))
    runs = json.loads((_nd(tmp_path) / "source_runs.json").read_text())
    assert len(runs) == 4 + 3  # history is appended, not replaced
    assert parquet_path(tmp_path, "crosswalk").exists()  # built from fresh ESPN + stored players
    with pytest.raises(ValueError, match="unknown sources"):
        refresh_all(tmp_path, sources=("yahoo",))
    with pytest.raises(ValueError):
        refresh_all(tmp_path, seasons=("2025",))


def test_failing_source_does_not_abort_others_or_touch_previous_files(tmp_path, fake_sources, monkeypatch):
    first = refresh_all(tmp_path, seasons=("2025-26",), include_playoffs=False)
    assert first.kept_previous == ()
    raw, meta_path = raw_paths(tmp_path, "espn_public", "players", "2027")
    raw_hash_before = sha256_hex(raw.read_bytes())
    meta_before = read_raw_meta(tmp_path, "espn_public", "players", "2027")
    espn_before = pd.read_parquet(parquet_path(tmp_path, "espn_players"))
    totals_before = parquet_path(tmp_path, "season_totals").read_bytes()

    def boom(season_id, client=None):
        raise FetchError("3 attempts failed; last error: ReadTimeout()")

    def totals_boom(season, season_type="Regular Season"):
        raise ConnectionError("stats.nba.com hung")

    monkeypatch.setattr(espn_public, "fetch_players_raw", boom)
    monkeypatch.setattr(nba_stats, "fetch_season_totals_raw", totals_boom)
    (raw.parent / "poison.json").write_text("{}")  # unrelated file must be left alone too
    second = refresh_all(tmp_path, seasons=("2025-26", "2024-25"), include_playoffs=False)

    failed = {(r.source, r.endpoint, r.key): r for r in second.failed_runs}
    assert set(failed) == {
        ("espn_public", "players", "2027"),
        ("nba_api", "leaguedashplayerstats", "2025-26_regular_season"),
        ("nba_api", "leaguedashplayerstats", "2024-25_regular_season"),
    }
    assert "ReadTimeout" in failed[("espn_public", "players", "2027")].error
    # the other fetches still ran and were written
    assert second.tables["players"] == 22 and second.tables["schedule"] == 6
    assert second.tables["game_logs"] == 24
    # failed fetches never overwrite raw files or metadata
    assert sha256_hex(raw.read_bytes()) == raw_hash_before
    assert read_raw_meta(tmp_path, "espn_public", "players", "2027") == meta_before
    assert (raw.parent / "poison.json").read_text() == "{}"
    # espn_players rebuilt from the cached raw (same content); season_totals kept previous because
    # 2024-25 has neither a fresh response nor a cache
    espn_after = pd.read_parquet(parquet_path(tmp_path, "espn_players"))
    pd.testing.assert_frame_equal(espn_after.drop(columns="fetched_at"), espn_before.drop(columns="fetched_at"))
    assert (espn_after["fetched_at"] == meta_before["fetched_at"]).all()
    assert parquet_path(tmp_path, "season_totals").read_bytes() == totals_before
    assert "season_totals" in second.kept_previous
    assert "season_totals" not in second.tables
    assert second.health["sources"]["espn_public"]["status"] == "partial"
    assert second.health["sources"]["nba_api"]["status"] == "partial"
    # crosswalk still built (players fresh, espn from cache)
    assert second.tables["crosswalk"] == 23


def test_failure_without_cache_or_previous_leaves_no_file(tmp_path, fake_sources, monkeypatch):
    def boom(season_id, client=None):
        raise FetchError("down")

    monkeypatch.setattr(espn_public, "fetch_players_raw", boom)
    monkeypatch.setattr(espn_public, "fetch_schedule_raw", boom)
    report = refresh_all(tmp_path, seasons=("2025-26",), include_playoffs=False)
    assert not parquet_path(tmp_path, "espn_players").exists()
    assert not parquet_path(tmp_path, "schedule").exists()
    assert not raw_paths(tmp_path, "espn_public", "players", "2027")[0].exists()
    assert parquet_path(tmp_path, "players").exists() and parquet_path(tmp_path, "game_logs").exists()
    assert not parquet_path(tmp_path, "crosswalk").exists()
    xw = [r for r in report.runs if r.endpoint == "crosswalk"][0]
    assert xw.status == "skipped" and "espn_players" in (xw.error or "")
    assert report.health["sources"]["espn_public"]["status"] == "failed"
    assert report.health["sources"]["nba_api"]["status"] == "ok"
    assert "FAILED espn_public/players/2027" in str(report)


def test_health_report_reads_what_exists(tmp_path, fake_sources):
    empty = health_report(tmp_path)
    assert all(not t["exists"] for t in empty["tables"].values())
    refresh_all(tmp_path, seasons=("2025-26",), include_playoffs=False)
    report = health_report(tmp_path)
    assert report["tables"]["players"]["rows"] == 22 and report["tables"]["schedule"]["exists"]
    assert report["coverage"]["unresolved_identities"] == 2
    assert report["source_runs_recorded"] == 6 and report["snapshot_date"]
