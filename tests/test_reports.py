"""AERVIGIA local synthetic reports, access roles and safe CSV regression."""

import csv
from datetime import datetime, timezone
from io import StringIO
import sqlite3

from fastapi.testclient import TestClient

from aervigia.app import create_app
from aervigia.auth import UserRegistry
from aervigia.core import Observation, Position, TrackStore
from aervigia.reports import collection_report, csv_cell, csv_report
from aervigia.storage import SQLiteEventJournal


def synthetic(oid="report-demo-1", latitude=0.0, longitude=0.0):
    return Observation(
        schema_version="0.1",
        observation_id=oid,
        source_id="sim",
        source_type="simulator",
        observed_at=datetime.now(timezone.utc),
        position=Position(latitude=latitude, longitude=longitude),
        position_uncertainty_m=12,
        simulation=True,
    )


def test_report_limits_fields_and_never_exports_positions():
    store = TrackStore()
    store.ingest(synthetic())
    alert = store.snapshot()["alerts"][0]
    report = collection_report([alert])
    assert report["simulation"] is True
    assert report["exported_count"] == 1
    assert report["totals"] == {"all": 1, "pending": 1, "acknowledged": 0, "closed": 0}
    record = report["incidents"][0]
    assert record["reference"] == alert["reference"]
    assert record["status"] == "pending"
    assert "latitude" not in str(report)
    assert "longitude" not in str(report)
    assert "position" not in str(report)
    assert "simulation" in record
    assert "SIMUL" in report["notice"]


def test_report_filters_and_csv_formula_injection():
    records = [
        {
            "reference": "INC-A", "status": "pending", "type": "zone-entry",
            "track_id": "=HYPERLINK(1,2)", "zone_id": "z", "at": "2026-11-17T11:00:00Z",
        },
        {
            "reference": "INC-B", "status": "closed", "type": "zone-entry",
            "track_id": "SIM-beta", "zone_id": "z", "at": "2026-11-17T11:00:01Z",
            "acknowledged_at": "2026-11-17T11:02:00Z", "acknowledged_by": "worker",
            "closed_at": "2026-11-17T11:03:00Z", "closed_by": "worker",
        },
    ]
    report = collection_report(records, "open")
    assert report["exported_count"] == 1
    assert report["totals"]["closed"] == 1
    assert collection_report(records, "closed")["exported_count"] == 1
    assert collection_report(records, "all")["exported_count"] == 2
    csv_bytes = csv_report(report).encode("utf-8")
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    decoded = csv_bytes.decode("utf-8-sig")
    rows = list(csv.DictReader(StringIO(decoded)))
    assert len(rows) == 1
    assert rows[0]["track_id"].startswith("'=HYPERLINK")
    for unsafe in ("=1+1", "+9", "-1", "@cmd", "\t=1"):
        assert csv_cell(unsafe).startswith("'")
    assert csv_cell(None) == ""
    assert csv_cell(True) == "TRUE"


def test_collection_is_explicitly_bounded():
    template = {
        "reference": "INC-demo", "status": "pending", "type": "zone-entry",
        "track_id": "sim", "zone_id": "zone", "at": "2026-11-17T10:00:00Z",
    }
    records = [{**template, "reference": f"INC-{i}"} for i in range(200)]
    report = collection_report(records, "all")
    assert report["exported_count"] == 80
    assert report["totals"]["all"] == 80
    assert "latest 80" in report["scope"]


def test_named_roles_gate_bulk_exports_but_viewers_can_see_one_report(tmp_path, monkeypatch):
    registry_path = tmp_path / "users.json"
    registry = UserRegistry(str(registry_path))
    viewer = registry.add("reportViewer", "viewer")
    operator = registry.add("reportOperator", "operator")
    monkeypatch.setenv("AERVIGIA_USERS_FILE", str(registry_path))
    monkeypatch.setenv("AERVIGIA_DB_PATH", str(tmp_path / "events.sqlite3"))
    monkeypatch.setenv("AERVIGIA_API_TOKEN", "legacy-does-not-bypass")
    vh = {"Authorization": f"Bearer {viewer}"}
    oh = {"Authorization": f"Bearer {operator}"}

    with TestClient(create_app(background=False)) as client:
        payload = synthetic().model_dump(mode="json")
        assert client.post("/api/observations", json=payload, headers=oh).status_code == 201
        alert = client.get("/api/state", headers=vh).json()["alerts"][0]
        base = "/api/reports/incidents"
        assert client.get(base + "/export", headers=vh).status_code == 403
        assert client.get(base + "/export").status_code == 401
        assert client.get(base + "/export", headers={"X-API-Key": "legacy-does-not-bypass"}).status_code == 401
        single = client.get(base + "/" + alert["reference"], headers=vh)
        assert single.status_code == 200
        assert single.json()["incident"]["status"] == "pending"
        assert "latitude" not in single.text
        assert client.get(base + "/missing", headers=vh).status_code == 404

        # Closing a reviewed incident is included in CSV and JSON.
        assert client.post(f"/api/alerts/{alert['id']}/ack", headers=oh).status_code == 200
        assert client.post(f"/api/incidents/{alert['id']}/close", headers=oh).status_code == 200
        json_report = client.get(base + "/export?format=json&status=closed", headers=oh)
        assert json_report.status_code == 200
        assert json_report.json()["exported_count"] == 1
        assert json_report.json()["incidents"][0]["closed_by"] == "reportOperator"
        assert "attachment" in json_report.headers["content-disposition"]
        assert json_report.headers["cache-control"] == "no-store"
        csv_download = client.get(base + "/export?format=csv&status=closed", headers=oh)
        assert csv_download.status_code == 200
        assert "text/csv" in csv_download.headers["content-type"]
        assert "reportOperator" in csv_download.text
        assert "latitude" not in csv_download.text
        assert "longitude" not in csv_download.text
        assert client.get(base + "/export?status=invalid", headers=oh).status_code == 422
        registry.revoke("reportOperator")
        assert client.get(base + "/export", headers=oh).status_code == 401


def test_runtime_retention_keeps_closed_status_on_replay(tmp_path):
    journal = SQLiteEventJournal(str(tmp_path / "journal.sqlite3"), retention_days=1)
    store = TrackStore(journal=journal)
    store.ingest(synthetic("outside", 0.04, 0.04))
    store.ingest(synthetic("inside", 0.0, 0.0))
    ref = store.snapshot()["alerts"][0]["reference"]
    aid = store.snapshot()["alerts"][0]["id"]
    store.acknowledge(aid, actor="op")
    store.close_incident(aid, actor="op")

    # Expire an unrelated earlier observation to trigger an in-memory rebuild.
    with sqlite3.connect(journal.path) as con:
        con.execute(
            "UPDATE journal_events SET recorded_at = ? WHERE event_id = ?",
            ("2000-01-01T00:00:00+00:00", "outside"),
        )
    assert store.maintain() == 1
    incident = store.snapshot()["alerts"][0]
    assert incident["reference"] == ref
    assert incident["status"] == "closed"
    assert incident["closed_by"] == "op"
    journal.close()
