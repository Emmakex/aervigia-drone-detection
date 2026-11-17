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
        assert client.post(f"/api/alerts/{aid}/ack", headers=headers).status_code == 200
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
