"""Deterministic, in-memory SIMULATED observations; no live drone collection."""

from collections import deque
from datetime import datetime, timezone
from math import sin
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Position(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Observation(BaseModel):
    """MVP accepts synthetic, explicitly labeled inputs ONLY."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1"]
    observation_id: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    source_type: Literal["simulator"]
    observed_at: datetime
    position: Position
    position_uncertainty_m: float = Field(ge=0, le=100000)
    classification: Literal["unknown", "quadcopter", "fixed-wing"] = "unknown"
    simulation: Literal[True]


# All locations here are fictional coordinates, not a deployment site.
ZONE = {
    "id": "SIM-ZONE-01",
    "name": "Zona de demostración",
    "min_lat": -0.01,
    "max_lat": 0.015,
    "min_lon": -0.015,
    "max_lon": 0.012,
    "simulation": True,
}


class TrackStore:
    """Thread-safe, bounded demo state. Not a multi-sensor fusion engine."""

    def __init__(self):
        self._lock = RLock()
        self._step = 0
        self._tracks = {}
        self._alerts = []
        self._events = deque(maxlen=150)
        self._inside = set()
        self._recent_observations = deque(maxlen=1000)
        self._seen_observations = set()
        self._alert_seq = 0

    def reset(self):
        with self._lock:
            self._step = 0
            self._tracks.clear()
            self._alerts.clear()
            self._events.clear()
            self._inside.clear()
            self._recent_observations.clear()
            self._seen_observations.clear()
            self._alert_seq = 0

    def ingest(self, observation: Observation):
        # Tracks are keyed by source. This is a demonstration, not sensor fusion.
        with self._lock:
            if observation.observation_id in self._seen_observations:
                return {"duplicate": True, "track_id": f"SIM-{observation.source_id}"}
            if len(self._recent_observations) == self._recent_observations.maxlen:
                oldest = self._recent_observations.popleft()
                self._seen_observations.discard(oldest)
            self._recent_observations.append(observation.observation_id)
            self._seen_observations.add(observation.observation_id)

            tid = f"SIM-{observation.source_id}"
            lat = observation.position.latitude
            lon = observation.position.longitude
            now = observation.observed_at.isoformat()
            track = self._tracks.get(tid)
            if track is None:
                track = {
                    "id": tid,
                    "source_id": observation.source_id,
                    "classification": observation.classification,
                    "simulation": True,
                    "last_seen": now,
                    "position": {"latitude": lat, "longitude": lon},
                    "uncertainty_m": observation.position_uncertainty_m,
                    "history": [],
                }
                self._tracks[tid] = track
                self._events.appendleft({"type": "new-track", "track_id": tid, "at": now})
            track["classification"] = observation.classification
            track["last_seen"] = now
            track["position"] = {"latitude": lat, "longitude": lon}
            track["uncertainty_m"] = observation.position_uncertainty_m
            track["history"].append({"latitude": lat, "longitude": lon})
            track["history"] = track["history"][-36:]

            inside = (ZONE["min_lat"] <= lat <= ZONE["max_lat"]
                      and ZONE["min_lon"] <= lon <= ZONE["max_lon"])
            if inside and tid not in self._inside:
                self._inside.add(tid)
                self._alert_seq += 1
                alert = {
                    "id": f"SIM-ALERT-{self._alert_seq:04d}",
                    "type": "zone-entry",
                    "title": "Entrada en zona simulada",
                    "track_id": tid,
                    "zone_id": ZONE["id"],
                    "at": now,
                    "acknowledged": False,
                    "simulation": True,
                }
                self._alerts.insert(0, alert)
                self._alerts = self._alerts[:80]
                self._events.appendleft({"type": "zone-entry", "track_id": tid, "at": now})
            elif not inside:
                self._inside.discard(tid)
            return {"duplicate": False, "track_id": tid}

    def acknowledge(self, alert_id: str) -> bool:
        with self._lock:
            for alert in self._alerts:
                if alert["id"] == alert_id:
                    if not alert["acknowledged"]:
                        alert["acknowledged"] = True
                        alert["acknowledged_at"] = utc_now()
                    return True
        return False

    def advance(self):
        """One reproducible step for TWO fictional aircraft tracks."""
        with self._lock:
            n = self._step
            self._step += 1
        # Reset simulated routes every 28 steps; no real-world coordinates.
        phase = n % 28
        paths = [
            ("alpha", 8 + phase * 3.2, 52 + sin(phase / 3) * 4, "quadcopter"),
            ("bravo", 87 - phase * 1.6, 19 + sin(phase / 4) * 5, "unknown"),
        ]
        for source, x, y, classification in paths:
            self.ingest(Observation(
                schema_version="0.1",
                observation_id=f"sim-{n}-{source}",
                source_id=source,
                source_type="simulator",
                observed_at=datetime.now(timezone.utc),
                position=Position(latitude=(y - 50) / 1000, longitude=(x - 50) / 1000),
                position_uncertainty_m=12.0,
                classification=classification,
                simulation=True,
            ))

    def snapshot(self):
        # Copy nested mutable structures while holding lock.
        with self._lock:
            tracks = []
            for track in self._tracks.values():
                tracks.append({
                    **track,
                    "position": dict(track["position"]),
                    "history": [dict(p) for p in track["history"]],
                })
            return {
                "mode": "simulation",
                "notice": "DEMO ONLY — fictional positions; not an operational detector",
                "generated_at": utc_now(),
                "tracks": sorted(tracks, key=lambda t: t["id"]),
                "zones": [dict(ZONE)],
                "alerts": [dict(a) for a in self._alerts[:25]],
                "events": [dict(e) for e in list(self._events)[:25]],
                "step": self._step,
            }
