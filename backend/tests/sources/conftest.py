"""Shared fixtures for source-adapter tests: recorded payloads and a hard network block."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.sources.base import RawResponse

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NBA_FIXTURES = FIXTURES / "nba_api"
ESPN_FIXTURES = FIXTURES / "espn_public"


def load_fixture(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def raw_from(path: Path, url: str = "https://example.invalid/fixture") -> RawResponse:
    body = path.read_bytes()
    return RawResponse(payload=json.loads(body), body=body, url=url, params={"fixture": path.name})


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs offline: any real HTTP attempt fails loudly."""

    def blocked(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network access is disabled in tests")

    monkeypatch.setattr(httpx.Client, "send", blocked)
    import nba_api.library.http as nba_http

    monkeypatch.setattr(nba_http.NBAHTTP, "send_api_request", blocked)


@pytest.fixture
def players_payload() -> dict:
    return load_fixture(NBA_FIXTURES / "commonallplayers_2026-27.json")


@pytest.fixture
def totals_payload() -> dict:
    return load_fixture(NBA_FIXTURES / "leaguedashplayerstats_2025-26.json")


@pytest.fixture
def game_logs_payload() -> dict:
    return load_fixture(NBA_FIXTURES / "playergamelogs_2025-26_regular_season.json")


@pytest.fixture
def espn_players_payload() -> list:
    return load_fixture(ESPN_FIXTURES / "players_2027.json")


@pytest.fixture
def espn_schedule_payload() -> dict:
    return load_fixture(ESPN_FIXTURES / "schedule_2027.json")
