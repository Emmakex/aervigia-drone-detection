"""Incident lifecycle and backward-compatible journal migration tests.

All observations and coordinates here are simulated laboratory fixtures.
"""

from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from aervigia.app import create_app
from aervigia.auth import UserRegistry
from aervigia.core import Observation, Position, TrackStore
from aervigia.storage import SQLiteEventJournal


def event(event_id: str):
    return Observation(
        schema_version="0.1",
        observation_id=event_id,
        source_id="test-aircraft",
        source_type="simulator",
        observed_at=datetime.now(timezone.utc),
        position=Position(latitude=0, longitude=0),
        position_uncertainty_m=6,
        classification="unknown",
        simulation=True,
    )


def test_incident_review_close_and_restart(tmp_path):
    path = str(tmp_path / "journal.sqlite3")
    journal = SQLiteEventJournal(path)
    store = TrackStore(journal=journal)
    store.ingest(event("unique-event-1"))
    incident = store.snapshot()["alerts"][0]
    assert incident["status"] == "pending"
    assert incident["reference"].startswith("INC-")
    assert store.close_incident(incident["id"], actor="opA") == "not_reviewed"

    assert store.acknowledge(incident["id"], actor="opA")
    assert store.acknowledge(incident["id"], actor="opA")
    assert store.close_incident(incident["id"], actor="opB") == "closed"
    assert store.close_incident(incident["id"], actor="opB") == "already_closed"
    result = store.snapshot()["alerts"][0]
    assert result["status"] == "closed"
    assert result["acknowledged_by"] == "opA"
    assert result["closed_by"] == "opB"
    assert journal.count() == 3
    assert [a["action"] for a in store.audit_actions()] == ["close", "ack"]
    journal.close()

    reopened = SQLiteEventJournal(path)
    reconstructed = TrackStore(journal=reopened)
    historic = reconstructed.snapshot()["alerts"][0]
    assert historic["reference"] == incident["reference"]
    assert historic["status"] == "closed"
    assert historic["closed_by"] == "opB"
    assert reconstructed.close_incident("nonexistent", actor="opA") == "not_found"
    reopened.close()


def test_public_incident_reference_stays_unique_across_simulation_reset():
    store = TrackStore()
    store.ingest(event("observation-one"))
    first = store.snapshot()["alerts"][0]["reference"]
    store.reset()
    store.ingest(event("observation-two"))
    second = store.snapshot()["alerts"][0]["reference"]
    assert first != second
    assert first.startswith("INC-")
    assert second.startswith("INC-")


def test_existing_sqlite_v02_database_is_migrated_in_place(tmp_path):
    path = str(tmp_path / "legacy.sqlite3")
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE journal_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('observation','ack','reset')),
                recorded_at TEXT NOT NULL,
                event_id TEXT UNIQUE,
                payload TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO journal_events(kind,recorded_at,event_id,payload) VALUES(?,?,?,?)",
            ("observation", datetime.now(timezone.utc).isoformat(), "legacy-1",
             event("legacy-1").model_dump_json()),
        )
    journal = SQLiteEventJournal(path)
    store = TrackStore(journal=journal)
    incident = store.snapshot()["alerts"][0]
    assert incident["status"] == "pending"
    store.acknowledge(incident["id"], actor="legacy-operator")
    assert store.close_incident(incident["id"], actor="legacy-operator") == "closed"
    assert journal.count() == 3
    journal.close()


def test_authenticated_close_endpoint_rejects_unreviewed_and_viewers(tmp_path, monkeypatch):
    user_file = tmp_path / "users.json"
    registry = UserRegistry(str(user_file))
    viewer = registry.add("viewerBeta", "viewer")
    operator = registry.add("operatorBeta", "operator")
    monkeypatch.setenv("AERVIGIA_USERS_FILE", str(user_file))
    monkeypatch.setenv("AERVIGIA_DB_PATH", str(tmp_path / "events.sqlite3"))
    viewer_headers = {"Authorization": f"Bearer {viewer}"}
    operator_headers = {"Authorization": f"Bearer {operator}"}

    with TestClient(create_app(background=False)) as client:
        # Explicitly only synthetic observations.
        sample = event("api-close-1").model_dump(mode="json")
        assert client.post("/api/observations", headers=operator_headers, json=sample).status_code == 201
        incident = client.get("/api/state", headers=viewer_headers).json()["alerts"][0]
        url = f"/api/incidents/{incident['id']}/close"
        assert client.post(url, headers=viewer_headers).status_code == 403
        response = client.post(url, headers=operator_headers)
        assert response.status_code == 409, response.text
        assert client.post(f"/api/alerts/{incident['id']}/ack", headers=operator_headers).status_code == 200
        assert client.post(url, headers=operator_headers).json() == {
            "id": incident["id"], "status": "closed", "already_closed": False
        }
        assert client.post(url, headers=operator_headers).json()["already_closed"] is True
        assert client.post("/api/incidents/nonexistent/close", headers=operator_headers).status_code == 404
        closed = client.get("/api/state", headers=viewer_headers).json()["alerts"][0]
        assert closed["status"] == "closed"
        assert closed["reference"] == incident["reference"]
        assert closed["closed_by"] == "operatorBeta"
        assert client.get("/api/audit", headers=viewer_headers).json()["actions"][0]["action"] == "close"

    with TestClient(create_app(background=False)) as client:
        restored = client.get("/api/state", headers=viewer_headers).json()["alerts"][0]
        assert restored["status"] == "closed"
        assert restored["closed_by"] == "operatorBeta"
