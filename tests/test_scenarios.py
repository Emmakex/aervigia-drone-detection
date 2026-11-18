"""Regression tests for simulation-only scenario selection and controls."""

from fastapi.testclient import TestClient

from aervigia.app import create_app
from aervigia.auth import UserRegistry
from aervigia.core import TrackStore
from aervigia.scenarios import DEFAULT_SCENARIO, SCENARIOS, catalog, scenario_paths
from aervigia.storage import SQLiteEventJournal


def test_all_presets_are_bounded_and_demo_only():
    assert DEFAULT_SCENARIO == "standard"
    assert set(SCENARIOS) == {"standard", "clear", "dual-entry"}
    assert all(scenario["simulation"] is True for scenario in catalog())
    for scenario_id in SCENARIOS:
        for step in range(28):
            for source, x, y, label in scenario_paths(scenario_id, step):
                assert source and label
                assert 0 <= x <= 100
                assert 0 <= y <= 100


def test_silent_scenario_has_no_zone_alerts():
    store = TrackStore()
    store.reset(scenario_id="clear")
    for _ in range(30):
        store.advance()
    state = store.snapshot()
    assert state["scenario_id"] == "clear"
    assert len(state["tracks"]) == 2
    assert state["alerts"] == []


def test_dual_entry_scenario_generates_distinct_simulated_incidents():
    store = TrackStore()
    store.reset(scenario_id="dual-entry")
    for _ in range(20):
        store.advance()
    state = store.snapshot()
    references = [item["reference"] for item in state["alerts"]]
    assert state["scenario_id"] == "dual-entry"
    assert len(state["tracks"]) == 3
    assert len(references) >= 2
    assert len(set(references)) == len(references)
    assert all(alert["simulation"] is True for alert in state["alerts"])


def test_pause_freezes_only_synthetic_ticks_then_resume():
    store = TrackStore()
    store.advance()
    old = store.snapshot()
    assert store.set_paused(True) is True
    assert store.advance() is False
    paused = store.snapshot()
    assert paused["paused"] is True
    assert paused["step"] == old["step"]
    assert paused["tracks"] == old["tracks"]
    assert store.set_paused(False) is False
    assert store.advance() is True
    assert store.snapshot()["step"] == old["step"] + 1


def test_selection_survives_database_restart_and_pause_is_ephemeral(tmp_path):
    path = str(tmp_path / "events.sqlite3")
    journal = SQLiteEventJournal(path)
    store = TrackStore(journal=journal)
    store.reset(scenario_id="dual-entry", actor="adminA")
    for _ in range(8):
        store.advance()
    before = store.snapshot()
    assert len(before["alerts"]) >= 2
    store.set_paused(True)
    assert store.snapshot()["paused"] is True
    journal.close()

    reopened = SQLiteEventJournal(path)
    restored = TrackStore(journal=reopened)
    result = restored.snapshot()
    assert result["scenario_id"] == "dual-entry"
    assert result["paused"] is False
    assert set(x["reference"] for x in result["alerts"]) == set(
        x["reference"] for x in before["alerts"]
    )
    assert restored.audit_actions()[0]["details"]["scenario_id"] == "dual-entry"
    restored.advance()
    assert restored.snapshot()["step"] == 1  # new process, new synthetic run
    reopened.close()


def test_reset_keeps_selected_scenario_and_rejects_invalid():
    store = TrackStore()
    store.reset(scenario_id="clear")
    store.advance()
    store.reset()
    assert store.snapshot()["scenario_id"] == "clear"
    assert store.snapshot()["step"] == 0
    try:
        store.reset(scenario_id="real-airport")
    except ValueError:
        pass
    else:
        raise AssertionError("Unrecognized scenario must be rejected")


def test_scenario_api_roles_and_pause_resume(tmp_path, monkeypatch):
    registry_path = tmp_path / "accounts.json"
    registry = UserRegistry(str(registry_path))
    viewer = registry.add("testViewer", "viewer")
    operator = registry.add("testOperator", "operator")
    admin = registry.add("testAdmin", "admin")
    monkeypatch.setenv("AERVIGIA_USERS_FILE", str(registry_path))
    monkeypatch.setenv("AERVIGIA_API_TOKEN", "legacy-bypass-must-fail")
    store = TrackStore()
    with TestClient(create_app(store, background=False)) as client:
        view = {"Authorization": "Bearer " + viewer}
        operate = {"Authorization": "Bearer " + operator}
        manage = {"Authorization": "Bearer " + admin}

        url = "/api/simulation/scenarios"
        assert client.get(url).status_code == 401
        listing = client.get(url, headers=view)
        assert listing.status_code == 200
        assert len(listing.json()["scenarios"]) == 3
        original_run_id = store.snapshot()["run_id"]
        body = {"expected_run_id": original_run_id}
        assert client.post(url + "/clear/start", headers=view, json=body).status_code == 403
        assert client.post(url + "/clear/start", headers=operate, json=body).status_code == 403
        assert client.post("/api/simulation/pause", headers=operate).status_code == 403
        assert client.post(url + "/clear/start", headers={"X-API-Key": "legacy-bypass-must-fail"}, json=body).status_code == 401
        assert client.post(url + "/bad-value/start", headers=manage, json=body).status_code == 404
        assert client.post(url + "/clear/start", headers=manage).status_code == 422

        start = client.post(url + "/clear/start", headers=manage, json=body)
        assert start.status_code == 200
        assert start.json()["scenario_id"] == "clear"
        assert store.snapshot()["step"] == 1
        assert start.json()["run_id"] != original_run_id

        # A second admin holding an old state cannot reset the active trial.
        stale = client.post(url + "/dual-entry/start", headers=manage, json=body)
        assert stale.status_code == 409
        assert store.snapshot()["scenario_id"] == "clear"
        assert store.snapshot()["step"] == 1

        paused = client.post("/api/simulation/pause", headers=manage)
        assert paused.status_code == 200 and paused.json()["paused"] is True
        assert store.advance() is False
        assert store.snapshot()["step"] == 1
        assert client.post("/api/simulation/resume", headers=manage).json()["paused"] is False
        assert store.advance() is True
        assert store.snapshot()["step"] == 2

        next_body = {"expected_run_id": store.snapshot()["run_id"]}
        assert client.post(url + "/dual-entry/start", headers=manage, json=next_body).status_code == 200
        assert client.get("/api/state", headers=view).json()["scenario_id"] == "dual-entry"
        assert store.snapshot()["step"] == 1
        assert client.post("/api/simulation/reset", headers=manage).json()["reset"] is True
        assert store.snapshot()["scenario_id"] == "dual-entry"

        registry.revoke("testAdmin")
        assert client.post(url + "/clear/start", headers=manage, json=body).status_code == 401
