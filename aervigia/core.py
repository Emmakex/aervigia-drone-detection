"""Deterministic synthetic observation engine with optional event replay."""

from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
from threading import RLock
from uuid import uuid4

from aervigia.scenarios import DEFAULT_SCENARIO, SCENARIOS, scenario_paths
from aervigia.storage import SQLiteEventJournal

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
    """Thread-safe demo state; optional SQLite replay. Not multi-sensor fusion."""

    def __init__(self, journal: SQLiteEventJournal | None = None):
        self._lock = RLock()
        self.journal = journal
        self._run_id = uuid4().hex[:12]
        self._scenario_id = DEFAULT_SCENARIO
        self._paused = False
        self._step = 0
        self._tracks = {}
        self._alerts = []
        self._events = deque(maxlen=150)
        self._inside = set()
        self._recent_observations = deque(maxlen=1000)
        self._seen_observations = set()
        self._alert_seq = 0
        if self.journal is not None:
            # A reset event is replayed in order, preserving only current history.
            for kind, payload in self.journal.iter_events():
                if kind == "observation":
                    self.ingest(Observation.model_validate(payload), replay=True)
                elif kind == "ack":
                    self.acknowledge(
                        payload["alert_id"], actor=payload["actor"],
                        at=payload["at"], replay=True
                    )
                elif kind == "close":
                    self.close_incident(
                        payload["alert_id"], actor=payload["actor"],
                        at=payload["at"], replay=True
                    )
                elif kind == "reset":
                    self.reset(replay=True, scenario_id=payload.get("scenario_id", DEFAULT_SCENARIO))

    def reset(
        self, replay: bool = False, actor: str = "local-operator",
        scenario_id: str | None = None,
    ):
        """Clear the current demo run. Scenario choice is journaled with reset."""
        with self._lock:
            next_id = scenario_id if scenario_id is not None else self._scenario_id
            if next_id not in SCENARIOS:
                raise ValueError("Unknown simulation scenario")
            if self.journal is not None and not replay:
                self.journal.append(
                    "reset", {"actor": actor, "at": utc_now(), "scenario_id": next_id}
                )
            self._scenario_id = next_id
            self._paused = False
            self._run_id = uuid4().hex[:12]
            self._step = 0
            self._tracks.clear()
            self._alerts.clear()
            self._events.clear()
            self._inside.clear()
            self._recent_observations.clear()
            self._seen_observations.clear()
            self._alert_seq = 0

    def start_scenario(
        self, scenario_id: str, expected_run_id: str, actor: str = "local-operator",
    ) -> dict | None:
        """Atomically compare-and-reset a synthetic scenario for one admin.

        None indicates another administrator has already replaced the run.
        Never journal a reset on a stale request.
        """
        with self._lock:
            if scenario_id not in SCENARIOS:
                raise ValueError("Unknown simulation scenario")
            if expected_run_id != self._run_id:
                return None
            self.reset(actor=actor, scenario_id=scenario_id)
            self.advance()
            return {
                "simulation": True,
                "scenario_id": scenario_id,
                "paused": False,
                "step": self._step,
                "run_id": self._run_id,
            }

    def set_paused(self, paused: bool, actor: str = "local-operator") -> bool:
        """Pause/resume locally without changing persistent incident evidence."""
        with self._lock:
            self._paused = bool(paused)
            self._events.appendleft({
                "type": "simulation-paused" if self._paused else "simulation-resumed",
                "track_id": "simulator", "actor": actor, "at": utc_now(),
            })
            return self._paused

    def ingest(self, observation: Observation, replay: bool = False):
        # Tracks are keyed by source. This is a demonstration, not sensor fusion.
        with self._lock:
            if observation.observation_id in self._seen_observations:
                return {"duplicate": True, "track_id": f"SIM-{observation.source_id}"}
            if self.journal is not None and not replay:
                if not self.journal.append(
                    "observation", observation.model_dump(mode="json"),
                    event_id=observation.observation_id,
                ):
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
                    # Public reference is unique across simulation resets and replays.
                    "reference": "INC-" + sha256(
                        observation.observation_id.encode("utf-8")
                    ).hexdigest()[:12].upper(),
                    "type": "zone-entry",
                    "title": "Entrada en zona simulada",
                    "track_id": tid,
                    "zone_id": ZONE["id"],
                    "at": now,
                    "acknowledged": False,
                    "closed": False,
                    "status": "pending",
                    "simulation": True,
                }
                self._alerts.insert(0, alert)
                self._alerts = self._alerts[:80]
                self._events.appendleft({"type": "zone-entry", "track_id": tid, "at": now})
            elif not inside:
                self._inside.discard(tid)
            return {"duplicate": False, "track_id": tid}

    def acknowledge(
        self, alert_id: str, actor: str = "local-operator",
        at: str | None = None, replay: bool = False,
    ) -> bool:
        with self._lock:
            for alert in self._alerts:
                if alert["id"] == alert_id:
                    if not alert["acknowledged"]:
                        stamp = at or utc_now()
                        if self.journal is not None and not replay:
                            self.journal.append(
                                "ack", {"alert_id": alert_id, "actor": actor, "at": stamp}
                            )
                        alert["acknowledged"] = True
                        alert["acknowledged_at"] = stamp
                        alert["acknowledged_by"] = actor
                        alert["status"] = "acknowledged"
                    return True
        return False

    def acknowledge_incident(
        self, alert_id: str, expected_reference: str,
        actor: str = "local-operator",
    ) -> str:
        """Reject a stale UI action before writing to the synthetic audit log."""
        with self._lock:
            for alert in self._alerts:
                if alert["id"] != alert_id:
                    continue
                if alert["reference"] != expected_reference:
                    return "stale"
                if alert["acknowledged"]:
                    return "already_acknowledged"
                self.acknowledge(alert_id, actor=actor)
                return "acknowledged"
            return "not_found"

    def close_incident(
        self, alert_id: str, actor: str = "local-operator",
        at: str | None = None, replay: bool = False,
        expected_reference: str | None = None,
    ) -> str:
        """Archive a reviewed simulated incident without deleting the evidence.

        Returns a machine-readable outcome, suitable for HTTP 404/409 mapping.
        """
        with self._lock:
            for alert in self._alerts:
                if alert["id"] != alert_id:
                    continue
                if expected_reference is not None and alert["reference"] != expected_reference:
                    return "stale"
                if alert["closed"]:
                    return "already_closed"
                if not alert["acknowledged"]:
                    return "not_reviewed"
                stamp = at or utc_now()
                if self.journal is not None and not replay:
                    self.journal.append(
                        "close", {
                            "alert_id": alert_id,
                            "reference": alert["reference"],
                            "actor": actor, "at": stamp,
                        }
                    )
                alert["closed"] = True
                alert["status"] = "closed"
                alert["closed_at"] = stamp
                alert["closed_by"] = actor
                self._events.appendleft({
                    "type": "incident-closed", "track_id": alert["track_id"],
                    "reference": alert["reference"], "at": stamp,
                })
                return "closed"
        return "not_found"

    def maintain(self) -> int:
        """Enforce retention during runtime and evict expired in-memory events.

        The journal is the source of truth. Locking preserves atomicity with
        simultaneous simulator ticks and operator reviews.
        """
        with self._lock:
            if self.journal is None:
                return 0
            removed = self.journal.purge_expired()
            if not removed:
                return 0
            saved_run, saved_step, saved_paused = self._run_id, self._step, self._paused
            self.reset(replay=True)
            for kind, payload in self.journal.iter_events():
                if kind == "observation":
                    self.ingest(Observation.model_validate(payload), replay=True)
                elif kind == "ack":
                    self.acknowledge(
                        payload["alert_id"], actor=payload["actor"],
                        at=payload["at"], replay=True,
                    )
                elif kind == "close":
                    self.close_incident(
                        payload["alert_id"], actor=payload["actor"],
                        at=payload["at"], replay=True
                    )
                elif kind == "reset":
                    self.reset(replay=True, scenario_id=payload.get("scenario_id", DEFAULT_SCENARIO))
            # Keep the running simulator's series continuous after maintenance.
            self._run_id, self._step, self._paused = saved_run, saved_step, saved_paused
            return removed

    def audit_actions(self, limit: int = 50) -> list[dict]:
        if self.journal is None:
            return []
        return self.journal.audit_actions(limit)

    def advance(self):
        """Produce one coherent, deterministic tick in the active fake scenario."""
        with self._lock:
            if self._paused:
                return False
            n = self._step
            run_id = self._run_id
            # Hold the same lock across both track updates so a scenario
            # reset cannot mix observations from the previous run.
            for source, x, y, classification in scenario_paths(self._scenario_id, n):
                self.ingest(Observation(
                    schema_version="0.1",
                    observation_id=f"sim-{run_id}-{n}-{source}",
                    source_id=source,
                    source_type="simulator",
                    observed_at=datetime.now(timezone.utc),
                    position=Position(latitude=(y - 50) / 1000, longitude=(x - 50) / 1000),
                    position_uncertainty_m=12.0,
                    classification=classification,
                    simulation=True,
                ))
            self._step += 1
            return True

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
                "persistence": self.journal is not None,
                "scenario_id": self._scenario_id,
                "scenario_name": SCENARIOS[self._scenario_id]["name"],
                "run_id": self._run_id,
                "paused": self._paused,
                "notice": "DEMO ONLY — fictional positions; not an operational detector",
                "generated_at": utc_now(),
                "tracks": sorted(tracks, key=lambda t: t["id"]),
                "zones": [dict(ZONE)],
                "alerts": [dict(a) for a in self._alerts[:80]],
                "events": [dict(e) for e in list(self._events)[:25]],
                "step": self._step,
            }
