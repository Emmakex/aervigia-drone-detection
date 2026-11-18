from datetime import datetime, timezone

from fastapi.testclient import TestClient

from aervigia.app import create_app
from aervigia.core import TrackStore


def payload():
    return {
        "schema_version": "0.1",
        "observation_id": "obs-api-001",
        "source_id": "demo",
        "source_type": "simulator",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "position": {"latitude": 0, "longitude": 0},
        "position_uncertainty_m": 10,
        "classification": "unknown",
        "simulation": True,
    }


def test_read_only_without_configured_key(monkeypatch):
    monkeypatch.delenv("AERVIGIA_API_TOKEN", raising=False)
    with TestClient(create_app(TrackStore(), background=False)) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        assert client.get("/api/state").status_code == 200
        assert client.post("/api/observations", json=payload()).status_code == 503


def test_authenticated_ingestion_and_ack(monkeypatch):
    monkeypatch.setenv("AERVIGIA_API_TOKEN", "secret-demo-token")
    with TestClient(create_app(TrackStore(), background=False)) as client:
        assert client.post("/api/observations", json=payload()).status_code == 401
        headers = {"X-API-Key": "secret-demo-token"}
        assert client.post("/api/observations", json=payload(), headers=headers).status_code == 201
        state = client.get("/api/state").json()
        assert len(state["tracks"]) == 1
        assert len(state["alerts"]) == 1
        aid = state["alerts"][0]["id"]
        assert client.post(f"/api/alerts/{aid}/ack", headers=headers, json={"expected_reference": state["alerts"][0]["reference"]}).status_code == 200
        assert client.get("/api/state").json()["alerts"][0]["acknowledged"] is True
        assert client.post("/api/simulation/reset", headers=headers).status_code == 200


def test_live_sources_are_explicitly_out_of_scope(monkeypatch):
    monkeypatch.setenv("AERVIGIA_API_TOKEN", "secret-demo-token")
    with TestClient(create_app(TrackStore(), background=False)) as client:
        real = payload()
        real["simulation"] = False
        real["source_type"] = "radar"
        assert client.post("/api/observations", json=real, headers={"X-API-Key": "secret-demo-token"}).status_code == 422


def test_dashboard_served(monkeypatch):
    monkeypatch.delenv("AERVIGIA_API_TOKEN", raising=False)
    with TestClient(create_app(TrackStore(), background=False)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "AERVIGIA" in response.text


def test_viewer_key_can_read_but_cannot_mutate(monkeypatch):
    monkeypatch.setenv("AERVIGIA_VIEW_TOKEN", "demo-viewer")
    monkeypatch.setenv("AERVIGIA_API_TOKEN", "demo-operator")
    with TestClient(create_app(TrackStore(), background=False)) as client:
        assert client.get("/api/state").status_code == 401
        assert client.get("/api/audit").status_code == 401
        assert client.get("/api/state", headers={"X-View-Key": "wrong"}).status_code == 401
        assert client.get("/api/state", headers={"X-View-Key": "demo-viewer"}).status_code == 200
        assert client.get("/api/audit", headers={"X-View-Key": "demo-viewer"}).status_code == 200
        assert client.get("/api/state", headers={"X-API-Key": "demo-operator"}).status_code == 200
        assert client.post("/api/observations", headers={"X-View-Key": "demo-viewer"}, json=payload()).status_code == 401


def test_persisted_incident_survives_application_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("AERVIGIA_DB_PATH", str(tmp_path / "events.sqlite3"))
    monkeypatch.setenv("AERVIGIA_VIEW_TOKEN", "demo-viewer")
    monkeypatch.setenv("AERVIGIA_API_TOKEN", "demo-operator")
    monkeypatch.setenv("AERVIGIA_OPERATOR_ID", "shift-lead")
    monkeypatch.setenv("AERVIGIA_RETENTION_DAYS", "7")
    viewer = {"X-View-Key": "demo-viewer"}
    operator = {"X-API-Key": "demo-operator"}
    with TestClient(create_app(background=False)) as client:
        assert client.post("/api/observations", json=payload(), headers=operator).status_code == 201
        alert = client.get("/api/state", headers=viewer).json()["alerts"][0]
        assert client.post(f"/api/alerts/{alert['id']}/ack", headers=operator, json={"expected_reference": alert["reference"]}).status_code == 200

    with TestClient(create_app(background=False)) as client:
        data = client.get("/api/state", headers=viewer).json()
        assert data["persistence"] is True
        assert data["alerts"][0]["acknowledged"] is True
        assert data["alerts"][0]["acknowledged_by"] == "shift-lead"
        audit = client.get("/api/audit", headers=viewer).json()
        assert audit["actions"][0]["details"]["actor"] == "shift-lead"
        assert client.post("/api/simulation/reset", headers=operator).status_code == 200

    with TestClient(create_app(background=False)) as client:
        assert client.get("/api/state", headers=viewer).json()["alerts"] == []
        assert client.get("/api/audit", headers=viewer).json()["actions"][0]["action"] == "reset"
