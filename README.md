# AERVIGIA

**Drone Detection & Airspace Intelligence**

AERVIGIA is an independent, hardware-agnostic software platform for **passive drone awareness, low-altitude airspace monitoring and incident management**. Its first release focuses on combining observations from authorized sources into a clear operational picture for human operators.

> **Status:** Project initialization / MVP planning. This repository does not yet contain a working detection system.

## Product goals

- Ingest authorized observations from Remote ID-compatible receivers and simulated sensors.
- Normalize incoming observations into a versioned, vendor-independent model.
- Correlate observations into tracks without overstating identification certainty.
- Visualize tracks and sensor provenance on a real-time map.
- Configure protected zones, authorized flights and human-reviewed alerts.
- Maintain an auditable incident history with appropriate retention controls.

## MVP v0.1 — narrowly scoped

1. **Simulation-first demo:** generate synthetic drone observation events for repeatable testing.
2. **Ingestion API:** receive and validate observation messages with a documented schema.
3. **Track service:** maintain current tracks, confidence and last-seen status.
4. **Operator dashboard:** map, active tracks, event timeline and incident list.
5. **Geofence alerts:** configurable zones and rules, with acknowledgment by an operator.
6. **Security baseline:** access control, logging, retention policies and CI tests.

Remote ID is an identification broadcast by participating aircraft; absence of Remote ID **must not** be treated as proof of malicious activity. A simulated system is not a certified airspace safety sensor.

## Architecture

```text
Approved sources / simulators
              |
        Ingestion API
              |
        Normalization
              |
      Correlation / tracks
              |
  +-----------+-----------+
  |           |           |
Map & UI   Alerts     Audit/history
```

See [MVP scope](docs/MVP.md) and [architecture decisions](docs/ARCHITECTURE.md).

## Guardrails

- Detection, visualization, safety-oriented analytics and operator support only.
- No automated engagement, weapon targeting or drone interdiction functionality.
- Never claim that a fused track is a verified identity without suitable evidence.
- Collect only lawfully available sensor data; apply access controls and data minimization.
- Integrations with live equipment require explicit authorization and applicable legal review.

## Project organization

The repository is intentionally separate from Kairoseth and other products. Public material is limited to general architecture and product planning; do not commit live sensor logs, deployment credentials, installation locations or personally identifying observations.

## Initial technology direction (proposal)

- API: Python + FastAPI, typed schemas.
- Web dashboard: Next.js + TypeScript.
- Data: PostgreSQL/PostGIS for tracks, areas and event records.
- Local development: Docker Compose.
- Testing: synthetic event fixtures with deterministic trajectories.

Technology choices remain proposals until validated in the first implementation issue.

## Roadmap

- [ ] Define synthetic observation schema and examples
- [ ] Implement an ingestion API with validation
- [ ] Build a working simulated track dashboard
- [ ] Add zone rules, event review and incident history
- [ ] Verify secure defaults, retention and CI

**Owner:** Emmakex · **Project:** AERVIGIA
