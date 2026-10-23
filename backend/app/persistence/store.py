"""SQLite-backed session store: append-only events, idempotency, optimistic concurrency, export."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from app.draft.events import SCHEMA_VERSION, DraftError, DraftState, Event, EventType, apply, now_iso, replay
from app.league.config import LeagueConfig
from app.league.strategy import Strategy

DDL = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  schema_version INTEGER NOT NULL, snapshot_id TEXT, league_json TEXT NOT NULL, strategy_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  session_id TEXT NOT NULL, seq INTEGER NOT NULL, type TEXT NOT NULL, payload_json TEXT NOT NULL,
  idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL, source TEXT NOT NULL,
  PRIMARY KEY (session_id, seq), UNIQUE (session_id, idempotency_key),
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS season_predictions (
  session_id TEXT NOT NULL, period INTEGER NOT NULL, home_manager_id TEXT NOT NULL, record_json TEXT NOT NULL,
  PRIMARY KEY (session_id, period, home_manager_id),
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS period_player_stats (
  session_id TEXT NOT NULL, period INTEGER NOT NULL, manager_id TEXT NOT NULL, player_id TEXT NOT NULL,
  record_json TEXT NOT NULL,
  PRIMARY KEY (session_id, period, manager_id, player_id),
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS session_sync (
  session_id TEXT PRIMARY KEY, league_id INTEGER, fetched_at TEXT, summary TEXT, record_json TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);
"""


class ConflictError(Exception):
    def __init__(self, expected: int, actual: int):
        super().__init__(f"revision conflict: expected {expected}, actual {actual}")
        self.expected, self.actual = expected, actual


class SessionStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(DDL)
        self._state_cache: dict[str, DraftState] = {}

    def close(self) -> None:
        self._conn.close()

    # --- sessions -------------------------------------------------------------------------
    def create_session(
        self,
        league: LeagueConfig,
        strategy: Strategy | None = None,
        snapshot_id: str | None = None,
        name: str | None = None,
        session_id: str | None = None,
    ) -> str:
        strategy = strategy or Strategy()
        sid = session_id or uuid.uuid4().hex[:12]
        ts = now_iso()
        with self._lock:
            self._conn.execute("BEGIN")
            self._conn.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
                (
                    sid,
                    name or league.name,
                    ts,
                    ts,
                    SCHEMA_VERSION,
                    snapshot_id,
                    league.model_dump_json(),
                    strategy.model_dump_json(),
                ),
            )
            self._conn.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                (
                    sid,
                    1,
                    EventType.session_created.value,
                    json.dumps({"snapshot_id": snapshot_id}),
                    f"created:{sid}",
                    ts,
                    "system",
                ),
            )
            self._conn.execute("COMMIT")
        return sid

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT s.id, s.name, s.created_at, s.updated_at, s.snapshot_id, "
            "(SELECT MAX(seq) FROM events e WHERE e.session_id = s.id) AS last_seq, "
            "(SELECT COUNT(*) FROM events e WHERE e.session_id = s.id AND e.type='pick_committed') AS n_commits "
            "FROM sessions s ORDER BY s.updated_at DESC"
        ).fetchall()
        return [
            dict(
                zip(("id", "name", "created_at", "updated_at", "snapshot_id", "last_seq", "n_commits"), r, strict=True)
            )
            for r in rows
        ]

    def session_meta(self, session_id: str) -> dict[str, Any] | None:
        r = self._conn.execute(
            "SELECT id, name, created_at, updated_at, snapshot_id, schema_version FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if r is None:
            return None
        return dict(zip(("id", "name", "created_at", "updated_at", "snapshot_id", "schema_version"), r, strict=True))

    def set_snapshot(self, session_id: str, snapshot_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET snapshot_id=?, updated_at=? WHERE id=?", (snapshot_id, now_iso(), session_id)
            )

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            self._conn.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            self._conn.execute("DELETE FROM session_sync WHERE session_id=?", (session_id,))
            self._conn.execute("DELETE FROM season_predictions WHERE session_id=?", (session_id,))
            self._conn.execute("DELETE FROM period_player_stats WHERE session_id=?", (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            self._conn.execute("COMMIT")
            self._state_cache.pop(session_id, None)

    # --- sync cache (bookkeeping only; never league truth) ---------------------------------
    def set_sync(self, session_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO session_sync VALUES (?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET "
                "league_id=excluded.league_id, fetched_at=excluded.fetched_at, summary=excluded.summary, "
                "record_json=excluded.record_json",
                (
                    session_id,
                    record.get("league_id"),
                    record.get("fetched_at"),
                    record.get("summary"),
                    json.dumps(record),
                ),
            )

    # --- weekly predictions log (frozen once a week starts; scored against ESPN later) --------
    def upsert_prediction(self, session_id: str, period: int, home_manager_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO season_predictions VALUES (?,?,?,?) "
                "ON CONFLICT(session_id, period, home_manager_id) DO UPDATE SET record_json=excluded.record_json",
                (session_id, period, home_manager_id, json.dumps(record)),
            )

    def predictions(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT record_json FROM season_predictions WHERE session_id=? ORDER BY period, home_manager_id",
            (session_id,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    # --- per-period applied player stats (ESPN box scores; history kept for every synced week) -----
    def upsert_period_player_stats(self, session_id: str, records: list[dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                for rec in records:
                    self._conn.execute(
                        "INSERT INTO period_player_stats VALUES (?,?,?,?,?) "
                        "ON CONFLICT(session_id, period, manager_id, player_id) DO UPDATE SET record_json=excluded.record_json",
                        (session_id, int(rec["period"]), rec["manager_id"], rec["player_id"], json.dumps(rec)),
                    )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def period_player_stats(
        self, session_id: str, period: int | None = None, manager_id: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT record_json FROM period_player_stats WHERE session_id=?"
        args: list[Any] = [session_id]
        if period is not None:
            sql += " AND period=?"
            args.append(int(period))
        if manager_id is not None:
            sql += " AND manager_id=?"
            args.append(manager_id)
        sql += " ORDER BY period, manager_id, player_id"
        return [json.loads(r[0]) for r in self._conn.execute(sql, args).fetchall()]

    def periods_with_stats(self, session_id: str) -> list[int]:
        rows = self._conn.execute(
            "SELECT DISTINCT period FROM period_player_stats WHERE session_id=? ORDER BY period", (session_id,)
        ).fetchall()
        return [int(r[0]) for r in rows]

    def get_sync(self, session_id: str) -> dict[str, Any] | None:
        r = self._conn.execute("SELECT record_json FROM session_sync WHERE session_id=?", (session_id,)).fetchone()
        return None if r is None else json.loads(r[0])

    # --- events ---------------------------------------------------------------------------
    def events(self, session_id: str) -> list[Event]:
        rows = self._conn.execute(
            "SELECT seq, type, payload_json, idempotency_key, created_at, source FROM events "
            "WHERE session_id=? ORDER BY seq",
            (session_id,),
        ).fetchall()
        return [Event(r[0], EventType(r[1]), json.loads(r[2]), r[3], r[4], r[5]) for r in rows]

    def _base(self, session_id: str) -> tuple[LeagueConfig, Strategy]:
        r = self._conn.execute("SELECT league_json, strategy_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if r is None:
            raise KeyError(session_id)
        return LeagueConfig.model_validate_json(r[0]), Strategy.model_validate_json(r[1])

    def state(self, session_id: str) -> DraftState:
        with self._lock:
            cached = self._state_cache.get(session_id)
            last = self._conn.execute("SELECT MAX(seq) FROM events WHERE session_id=?", (session_id,)).fetchone()[0]
            if cached is not None and cached.last_seq == last:
                return cached
            league, strategy = self._base(session_id)
            st = replay(league, self.events(session_id), strategy)
            self._state_cache[session_id] = st
            return st

    def append(
        self,
        session_id: str,
        type: EventType,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        source: str = "manual",
    ) -> tuple[Event, DraftState, bool]:
        """Validate against the current state and append. Returns (event, new_state, deduplicated).

        ``expected_revision`` is the client's last seen ``last_seq``; mismatch raises ConflictError.
        A repeated ``idempotency_key`` returns the stored event without re-applying.
        """
        key = idempotency_key or uuid.uuid4().hex
        with self._lock:
            existing = self._conn.execute(
                "SELECT seq, type, payload_json, idempotency_key, created_at, source FROM events "
                "WHERE session_id=? AND idempotency_key=?",
                (session_id, key),
            ).fetchone()
            if existing:
                ev = Event(
                    existing[0], EventType(existing[1]), json.loads(existing[2]), existing[3], existing[4], existing[5]
                )
                return ev, self.state(session_id), True
            st = self.state(session_id)
            if expected_revision is not None and expected_revision != st.last_seq:
                raise ConflictError(expected_revision, st.last_seq)
            ev = Event(st.last_seq + 1, type, payload, key, now_iso(), source)
            new_state = apply(st, ev)  # raises DraftError on invalid
            self._conn.execute("BEGIN")
            self._conn.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                (session_id, ev.seq, ev.type.value, json.dumps(ev.payload), key, ev.created_at, source),
            )
            self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (ev.created_at, session_id))
            self._conn.execute("COMMIT")
            self._state_cache[session_id] = new_state
            return ev, new_state, False

    def append_batch(
        self,
        session_id: str,
        items: list[tuple[EventType, dict[str, Any], str | None]],
        expected_revision: int | None = None,
        source: str = "import",
    ) -> DraftState:
        """Atomic batch: all events validate and persist, or none do."""
        with self._lock:
            st = self.state(session_id)
            if expected_revision is not None and expected_revision != st.last_seq:
                raise ConflictError(expected_revision, st.last_seq)
            evs: list[Event] = []
            cur = st
            for t, payload, key in items:
                ev = Event(cur.last_seq + 1, t, payload, key or uuid.uuid4().hex, now_iso(), source)
                cur = apply(cur, ev)
                evs.append(ev)
            self._conn.execute("BEGIN")
            try:
                for ev in evs:
                    self._conn.execute(
                        "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                        (
                            session_id,
                            ev.seq,
                            ev.type.value,
                            json.dumps(ev.payload),
                            ev.idempotency_key,
                            ev.created_at,
                            source,
                        ),
                    )
                self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now_iso(), session_id))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            self._state_cache[session_id] = cur
            return cur

    # --- export / import --------------------------------------------------------------------
    def export_session(self, session_id: str) -> dict[str, Any]:
        meta = self.session_meta(session_id)
        if meta is None:
            raise KeyError(session_id)
        league, strategy = self._base(session_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": now_iso(),
            "session": meta,
            "league": league.model_dump(mode="json"),
            "strategy": strategy.model_dump(mode="json"),
            "events": [e.to_dict() for e in self.events(session_id)],
        }

    def import_session(self, data: dict[str, Any], new_id: bool = True) -> str:
        if int(data.get("schema_version", 0)) != SCHEMA_VERSION:
            raise DraftError("schema_version", f"unsupported export schema {data.get('schema_version')}")
        league = LeagueConfig.model_validate(data["league"])
        strategy = Strategy.model_validate(data.get("strategy", {}))
        events = [Event.from_dict(e) for e in data["events"]]
        replay(league, events, strategy)  # validate the whole history before writing anything
        sid = uuid.uuid4().hex[:12] if new_id else data["session"]["id"]
        meta = data["session"]
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
                    (
                        sid,
                        meta.get("name", league.name),
                        meta.get("created_at", now_iso()),
                        now_iso(),
                        SCHEMA_VERSION,
                        meta.get("snapshot_id"),
                        league.model_dump_json(),
                        strategy.model_dump_json(),
                    ),
                )
                for ev in events:
                    self._conn.execute(
                        "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                        (
                            sid,
                            ev.seq,
                            ev.type.value,
                            json.dumps(ev.payload),
                            ev.idempotency_key,
                            ev.created_at,
                            ev.source,
                        ),
                    )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return sid
