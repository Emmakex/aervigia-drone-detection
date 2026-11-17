"""Small SQLite event journal for a local, simulation-only demonstration.

Stores synthetic observations and operator actions. It is not a tamper-evident
or safety-certified audit trail. No external DB or ORM is required.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock


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
                    kind TEXT NOT NULL CHECK(kind IN ('observation', 'ack', 'reset')),
                    recorded_at TEXT NOT NULL,
                    event_id TEXT UNIQUE,
                    payload TEXT NOT NULL
                )
            """)
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS journal_events_recorded_at_idx "
                "ON journal_events(recorded_at)"
            )
            self._conn.commit()
            self.purge_expired()

    def purge_expired(self):
        """Purge expired rows on startup; no automatic archival beyond retention."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM journal_events WHERE recorded_at < ?", (cutoff,)
            )
            self._conn.commit()
            return cursor.rowcount

    def append(self, kind: str, payload: dict, event_id: str | None = None) -> bool:
        if kind not in {"observation", "ack", "reset"}:
            raise ValueError("Unsupported journal event")
        if kind == "observation" and not event_id:
            raise ValueError("Observation requires event_id")
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
                "WHERE kind IN ('ack','reset') ORDER BY seq DESC LIMIT ?",
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
