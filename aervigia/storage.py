"""Small SQLite event journal for a local, simulation-only demonstration.

Stores synthetic observations and operator actions. It is not a tamper-evident
or safety-certified audit trail. No external DB or ORM is required.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock

from aervigia.scenarios import DEFAULT_SCENARIO, SCENARIOS


class SQLiteEventJournal:
    def __init__(self, path: str, retention_days: int = 7):
        if not 1 <= retention_days <= 30:
            raise ValueError("retention_days must be between 1 and 30")
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._lock = RLock()
        self._conn = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=15000")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('observation', 'ack', 'reset', 'close')),
                    recorded_at TEXT NOT NULL,
                    event_id TEXT UNIQUE,
                    payload TEXT NOT NULL
                )
            """)
            # Databases created by v0.2 have a CHECK without 'close'.
            # A small transactional table rewrite preserves all existing sequence IDs.
            ddl = self._conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='journal_events'"
            ).fetchone()[0]
            if "'close'" not in ddl:
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    self._conn.execute("""
                        CREATE TABLE journal_events_v03 (
                            seq INTEGER PRIMARY KEY AUTOINCREMENT,
                            kind TEXT NOT NULL CHECK(kind IN ('observation', 'ack', 'reset', 'close')),
                            recorded_at TEXT NOT NULL,
                            event_id TEXT UNIQUE,
                            payload TEXT NOT NULL
                        )
                    """)
                    self._conn.execute(
                        "INSERT INTO journal_events_v03(seq,kind,recorded_at,event_id,payload) "
                        "SELECT seq,kind,recorded_at,event_id,payload FROM journal_events"
                    )
                    self._conn.execute("DROP TABLE journal_events")
                    self._conn.execute(
                        "ALTER TABLE journal_events_v03 RENAME TO journal_events"
                    )
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS journal_events_recorded_at_idx "
                "ON journal_events(recorded_at)"
            )
            # A single durable setting survives journal event expiry. A
            # pre-v0.5.3 database is backfilled BEFORE removing expired
            # reset events so its last selected scenario is not forgotten.
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            current = self._conn.execute(
                "SELECT value FROM journal_meta WHERE key='active_scenario'"
            ).fetchone()
            if current is None:
                last_reset = self._conn.execute(
                    "SELECT payload FROM journal_events WHERE kind='reset' "
                    "ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                scenario_id = (
                    json.loads(last_reset[0]).get("scenario_id", DEFAULT_SCENARIO)
                    if last_reset else DEFAULT_SCENARIO
                )
                if scenario_id not in SCENARIOS:
                    raise ValueError("Unknown persisted simulation scenario")
                self._conn.execute(
                    "INSERT INTO journal_meta(key,value) VALUES('active_scenario',?)",
                    (scenario_id,),
                )
            self._conn.commit()
            self.purge_expired()

    def active_scenario(self) -> str:
        """Read the currently selected demo preset, independent of event retention."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM journal_meta WHERE key='active_scenario'"
            ).fetchone()
            if row is None or row[0] not in SCENARIOS:
                raise ValueError("Invalid persisted simulation scenario")
            return row[0]

    def purge_expired(self):
        """Purge expired journal rows; active scenario metadata is unaffected."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM journal_events WHERE recorded_at < ?", (cutoff,)
            )
            self._conn.commit()
            return cursor.rowcount

    def append(self, kind: str, payload: dict, event_id: str | None = None) -> bool:
        if kind not in {"observation", "ack", "reset", "close"}:
            raise ValueError("Unsupported journal event")
        if kind == "observation" and not event_id:
            raise ValueError("Observation requires event_id")
        if kind == "reset" and payload.get("scenario_id", DEFAULT_SCENARIO) not in SCENARIOS:
            raise ValueError("Unknown simulation scenario")
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO journal_events(kind,recorded_at,event_id,payload) "
                    "VALUES(?,?,?,?)",
                    (
                        kind,
                        datetime.now(timezone.utc).isoformat(),
                        event_id,
                        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                    ),
                )
                if kind == "reset":
                    # Reset event and active preset change share a transaction.
                    self._conn.execute(
                        "UPDATE journal_meta SET value=? WHERE key='active_scenario'",
                        (payload.get("scenario_id", DEFAULT_SCENARIO),),
                    )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                if kind == "observation" and event_id:
                    row = self._conn.execute(
                        "SELECT 1 FROM journal_events WHERE event_id = ?", (event_id,)
                    ).fetchone()
                    if row:
                        return False
                raise

    def iter_events(self):
        """Yield oldest-first events for deterministic reconstruction."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind,payload FROM journal_events ORDER BY seq"
            ).fetchall()
        for kind, payload in rows:
            yield kind, json.loads(payload)

    def audit_actions(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind,recorded_at,payload FROM journal_events "
                "WHERE kind IN ('ack','reset','close') ORDER BY seq DESC LIMIT ?",
                (min(max(1, limit), 100),),
            ).fetchall()
        return [
            {"action": kind, "recorded_at": stamp, "details": json.loads(payload)}
            for kind, stamp, payload in rows
        ]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM journal_events").fetchone()[0]

    def close(self):
        with self._lock:
            self._conn.close()
