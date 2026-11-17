from datetime import datetime, timezone

from aervigia.core import Observation, Position, TrackStore


def observation(oid, source, lat, lon):
    return Observation(
        schema_version="0.1",
        observation_id=oid,
        source_id=source,
        source_type="simulator",
        observed_at=datetime.now(timezone.utc),
        position=Position(latitude=lat, longitude=lon),
        position_uncertainty_m=15,
        classification="unknown",
        simulation=True,
    )


def test_simulator_creates_two_tracks_without_real_sources():
    engine = TrackStore()
    engine.advance()
    state = engine.snapshot()
    assert len(state["tracks"]) == 2
    assert state["mode"] == "simulation"
    assert all(t["simulation"] for t in state["tracks"])


def test_zone_alert_only_on_entry_and_can_acknowledge():
    engine = TrackStore()
    engine.ingest(observation("o1", "alpha", -0.03, -0.03))
    engine.ingest(observation("o2", "alpha", 0.0, 0.0))
    engine.ingest(observation("o3", "alpha", 0.001, 0.001))
    assert len(engine.snapshot()["alerts"]) == 1
    alert_id = engine.snapshot()["alerts"][0]["id"]
    assert engine.acknowledge(alert_id)
    assert engine.snapshot()["alerts"][0]["acknowledged"] is True
    assert not engine.acknowledge("missing")

    engine.ingest(observation("o4", "alpha", 0.04, 0.04))
    engine.ingest(observation("o5", "alpha", 0.0, 0.0))
    assert len(engine.snapshot()["alerts"]) == 2


def test_duplicate_event_is_idempotent():
    engine = TrackStore()
    event = observation("same-id", "bravo", 0.0, 0.0)
    assert engine.ingest(event)["duplicate"] is False
    assert engine.ingest(event)["duplicate"] is True
    assert len(engine.snapshot()["tracks"][0]["history"]) == 1


def test_reset_clears_alerts_and_tracks():
    engine = TrackStore()
    engine.ingest(observation("o1", "alpha", 0, 0))
    engine.reset()
    state = engine.snapshot()
    assert not state["tracks"] and not state["alerts"]
