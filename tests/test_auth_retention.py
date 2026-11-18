"""Named-user RBAC regression coverage; synthetic events only."""

from datetime import datetime, timezone
import json
import sqlite3

from fastapi.testclient import TestClient

from aervigia.app import create_app
from aervigia.auth import UserRegistry
from aervigia.core import Observation, Position, TrackStore
from aervigia.storage import SQLiteEventJournal


def sample(oid="named-obs-1"):
    return {
        "schema_version": "0.1",
        "observation_id": oid,
        "source_id": "named-demo",
        "source_type": "simulator",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "position": {"latitude": 0, "longitude": 0},
        "position_uncertainty_m": 10,
        "classification": "unknown",
        "simulation": True,
    }


def bearer(token):
    return {"Authorization": "Bearer " + token}


def test_registry_stores_hashes_and_revokes_immediately(tmp_path):
    path = tmp_path / "users.json"
    registry = UserRegistry(str(path))
    token = registry.add("operatorOne", "operator")
    raw = path.read_text()
    assert token not in raw
    assert len(token) >= 32
    assert json.loads(raw)["users"][0]["role"] == "operator"
    identity = registry.authenticate("Bearer " + token)
    assert identity.user_id == "operatorOne"
    assert identity.role == "operator"
    assert registry.revoke("operatorOne") is True
    try:
        registry.authenticate("Bearer " + token)
    except PermissionError:
        pass
    else:
        raise AssertionError("Revoked account must not authenticate")


def test_named_account_permissions_and_audited_actor(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    registry = UserRegistry(str(users))
    viewer = registry.add("viewerOne", "viewer")
    operator = registry.add("operatorOne", "operator")
    admin = registry.add("adminOne", "admin")

    monkeypatch.setenv("AERVIGIA_USERS_FILE", str(users))
    monkeypatch.setenv("AERVIGIA_DB_PATH", str(tmp_path / "journal.sqlite3"))
    monkeypatch.setenv("AERVIGIA_API_TOKEN", "old-shared-operator-key")
    monkeypatch.setenv("AERVIGIA_VIEW_TOKEN", "old-shared-view-key")
    with TestClient(create_app(background=False)) as client:
        assert client.get("/api/auth-mode").json()["mode"] == "named"
        assert client.get("/api/state").status_code == 401
        assert client.get("/api/state", headers={"X-View-Key": "old-shared-view-key"}).status_code == 401
        assert client.post("/api/observations", headers={"X-API-Key": "old-shared-operator-key"}, json=sample()).status_code == 401
        assert client.get("/api/me", headers=bearer(viewer)).json() == {"user_id": "viewerOne", "role": "viewer"}
        assert client.get("/api/state", headers=bearer(viewer)).status_code == 200
        assert client.post("/api/observations", headers=bearer(viewer), json=sample()).status_code == 403
        assert client.post("/api/observations", headers=bearer(operator), json=sample()).status_code == 201
        alert = client.get("/api/state", headers=bearer(viewer)).json()["alerts"][0]
        alert_id = alert["id"]
        assert client.post(f"/api/alerts/{alert_id}/ack", headers=bearer(operator), json={"expected_reference": alert["reference"]}).status_code == 200
        assert client.post("/api/simulation/reset", headers=bearer(operator)).status_code == 403
        audited = client.get("/api/audit", headers=bearer(viewer)).json()
        assert audited["actions"][0]["details"]["actor"] == "operatorOne"
        assert client.post("/api/simulation/reset", headers=bearer(admin)).status_code == 200
        audited = client.get("/api/audit", headers=bearer(admin)).json()
        assert audited["actions"][0]["action"] == "reset"
        assert audited["actions"][0]["details"]["actor"] == "adminOne"

        registry.revoke("operatorOne")
        assert client.get("/api/me", headers=bearer(operator)).status_code == 401
        assert client.get("/api/state", headers=bearer(viewer)).status_code == 200


def test_missing_registry_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("AERVIGIA_USERS_FILE", str(tmp_path / "not-created.json"))
    monkeypatch.setenv("AERVIGIA_VIEW_TOKEN", "old-legacy-token")
    with TestClient(create_app(TrackStore(), background=False)) as client:
        assert client.get("/api/state", headers={"X-View-Key": "old-legacy-token"}).status_code == 401
        assert client.get("/api/state", headers=bearer("x" * 40)).status_code == 503


def test_invalid_registry_schema_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    path.write_text('{"schema_version": 99, "users": []}')
    monkeypatch.setenv("AERVIGIA_USERS_FILE", str(path))
    with TestClient(create_app(TrackStore(), background=False)) as client:
        assert client.get("/api/me", headers=bearer("x" * 40)).status_code == 503


def test_runtime_retention_rebuilds_memory_without_restarting(tmp_path):
    journal = SQLiteEventJournal(str(tmp_path / "journal.sqlite3"), retention_days=1)
    store = TrackStore(journal=journal)
    for oid in ("old-observation", "new-observation"):
        store.ingest(Observation(
            schema_version="0.1",
            observation_id=oid,
            source_id="sim",
            source_type="simulator",
            observed_at=datetime.now(timezone.utc),
            position=Position(latitude=0.0, longitude=0.0),
            position_uncertainty_m=4,
            simulation=True,
        ))
    assert len(store.snapshot()["tracks"][0]["history"]) == 2
    with sqlite3.connect(journal.path) as conn:
        conn.execute("UPDATE journal_events SET recorded_at = ? WHERE event_id = ?",
                     ("2000-01-01T00:00:00+00:00", "old-observation"))
    before_step = store.snapshot()["step"]
    assert store.maintain() == 1
    assert store.snapshot()["step"] == before_step
    assert len(store.snapshot()["tracks"][0]["history"]) == 1
    assert journal.count() == 1
    assert store.maintain() == 0
    journal.close()
