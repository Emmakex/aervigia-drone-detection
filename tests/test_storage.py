from datetime import datetime, timedelta, timezone
import json
import sqlite3

from aervigia.core import Observation, Position, TrackStore
from aervigia.storage import SQLiteEventJournal


def obs(oid: str, lat: float = 0.0, lon: float = 0.0):
    return Observation(
        schema_version="0.1",
        observation_id=oid,
        source_id="alpha",
        source_type="simulator",
        observed_at=datetime.now(timezone.utc),
        position=Position(latitude=lat, longitude=lon),
        position_uncertainty_m=10,
        classification="quadcopter",
        simulation=True,
    )


def test_persistence_restores_alerts_and_operator_actions(tmp_path):
    db = str(tmp_path / "events.sqlite3")
    journal = SQLiteEventJournal(db, retention_days=7)
    engine = TrackStore(journal=journal)
    sample = obs("unique-1")
    assert engine.ingest(sample)["duplicate"] is False
    assert engine.acknowledge("SIM-ALERT-0001", actor="test-operator")
    assert engine.snapshot()["alerts"][0]["acknowledged_by"] == "test-operator"
    assert journal.count() == 2
    journal.close()

    reopened = SQLiteEventJournal(db)
    restored = TrackStore(journal=reopened)
    state = restored.snapshot()
    assert len(state["tracks"]) == 1
    assert len(state["alerts"]) == 1
    assert state["alerts"][0]["acknowledged"]
    assert state["alerts"][0]["acknowledged_by"] == "test-operator"
    assert state["persistence"] is True
    assert restored.ingest(sample)["duplicate"] is True
    assert reopened.count() == 2
    assert restored.audit_actions()[0]["details"]["actor"] == "test-operator"
    reopened.close()


def test_reset_persists_and_subsequent_events_rebuild(tmp_path):
    db = str(tmp_path / "events.sqlite3")
    journal = SQLiteEventJournal(db)
    store = TrackStore(journal=journal)
    store.ingest(obs("before-reset"))
    store.reset(actor="test-operator")
    assert store.snapshot()["tracks"] == []
    store.ingest(obs("after-reset", lat=0.03, lon=0.03))
    journal.close()

    reopened = SQLiteEventJournal(db)
    store2 = TrackStore(journal=reopened)
    assert len(store2.snapshot()["tracks"]) == 1
    assert store2.snapshot()["tracks"][0]["history"] == [
        {"latitude": 0.03, "longitude": 0.03}
    ]
    assert len(store2.snapshot()["alerts"]) == 0
    assert store2.audit_actions()[0]["action"] == "reset"
    reopened.close()


def test_startup_retention_purges_expired_records(tmp_path):
    db = str(tmp_path / "events.sqlite3")
    journal = SQLiteEventJournal(db, retention_days=1)
    journal.append("observation", obs("old").model_dump(mode="json"), event_id="old")
    journal.append("observation", obs("new").model_dump(mode="json"), event_id="new")
    journal.close()
    old_date = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE journal_events SET recorded_at = ? WHERE event_id = 'old'",
            (old_date,),
        )
    reopened = SQLiteEventJournal(db, retention_days=1)
    state = TrackStore(journal=reopened).snapshot()
    assert len(state["tracks"]) == 1
    assert len(state["tracks"][0]["history"]) == 1
    assert reopened.count() == 1
    reopened.close()


def test_simulator_event_ids_do_not_collide_after_reset_or_restart(tmp_path):
    db = str(tmp_path / "events.sqlite3")
    journal = SQLiteEventJournal(db)
    store = TrackStore(journal=journal)
    store.advance()
    assert journal.count() == 2
    store.reset()
    store.advance()
    assert journal.count() == 5  # 2 observations + reset + 2 observations
    journal.close()
    reopened = SQLiteEventJournal(db)
    restored = TrackStore(journal=reopened)
    restored.advance()
    assert reopened.count() == 7
    reopened.close()



def test_legacy_database_backfills_scenario_before_expiring_reset(tmp_path):
    """Upgrade a v0.5.2 journal that never had a separate scenario setting."""
    db = str(tmp_path / "previous-version.sqlite3")
    recent = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE journal_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('observation','ack','reset','close')),
                recorded_at TEXT NOT NULL,
                event_id TEXT UNIQUE,
                payload TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO journal_events(kind,recorded_at,payload) VALUES(?,?,?)",
            ("reset", old, json.dumps({
                "actor": "oldAdmin", "at": old, "scenario_id": "clear",
            })),
        )
        conn.execute(
            "INSERT INTO journal_events(kind,recorded_at,event_id,payload) "
            "VALUES(?,?,?,?)",
            ("observation", recent, "after-old-reset",
             json.dumps(obs("after-old-reset", lat=0.03, lon=0.03).model_dump(mode="json"))),
        )

    upgraded = SQLiteEventJournal(db, retention_days=1)
    assert upgraded.count() == 1  # Historical reset event respects retention.
    assert upgraded.active_scenario() == "clear"
    store = TrackStore(journal=upgraded)
    assert store.snapshot()["scenario_id"] == "clear"
    assert len(store.snapshot()["tracks"]) == 1
    upgraded.close()

    # Also valid on a subsequent startup, with no remaining reset event.
    reopened = SQLiteEventJournal(db, retention_days=1)
    assert TrackStore(journal=reopened).snapshot()["scenario_id"] == "clear"
    reopened.close()
