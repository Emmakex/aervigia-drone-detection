# AERVIGIA MVP v0.1 — Scope and Acceptance

## Target user

An authorized infrastructure security team or airspace operations analyst who needs consolidated situational awareness rather than several unrelated sensor screens.

## Goal

Demonstrate end-to-end processing of **synthetic observations** on a map with human-reviewed alerts and repeatable tests. This MVP does not claim real-world sensor detection performance.

## Features included

| Capability | MVP definition | Acceptance criterion |
| --- | --- | --- |
| Input | JSON observation endpoint and deterministic simulator | Invalid payloads rejected with a clear error |
| Observation | timestamp, sensor ID, type, optional position, uncertainty and provenance | Required fields documented and validated |
| Track | Stable track ID, estimated position, status, last-seen and evidence | Can follow at least two simultaneous simulated tracks |
| Map | Sensor-independent tracks and history | Operator can distinguish fresh vs stale observations |
| Zones | Polygon geofences, authorized test zones | A simulated boundary crossing produces a reviewable event |
| Alert | Severity, rule trigger, source and acknowledgment | Operator can acknowledge without deleting the event |
| Evidence | Basic event log and track history | Origin and time of each observation remain accessible |
| Security | Auth, least privilege, retention and audit trail | No anonymous write access to ingest or administration |

## Excluded from MVP

- Jamming, takeover, disabling, weapon integration or automated engagement.
- Live vendor-specific radar/RF/EO-IR hardware connectors.
- Claims of positive identity or threat attribution from a missing Remote ID.
- Predictive designation of targets or autonomous response.
- Procurement, deployment or monitoring in sensitive live locations.

## Operating principles

1. **Human-in-the-loop:** the operator reviews incidents and alerts.
2. **Uncertainty displayed:** confidence and timestamps always accompany track estimates.
3. **No fabricated data:** use explicit simulated-source labeling.
4. **Data provenance:** preserve sensor and transform history for troubleshooting.
5. **Privacy by default:** minimize personal data and configure retention.
6. **Reliable core over features:** avoid expanding scope until the demo is demonstrably stable.

## Definition of Done

A developer can start the local demo, load synthetic scenarios, view tracks on a map, test a geofence alert, acknowledge it and retrieve a reproducible incident history. Automated tests pass and setup is documented.
