# AERVIGIA

**Drone Detection & Airspace Intelligence**

AERVIGIA is an independent, hardware-agnostic software platform for **passive drone awareness, low-altitude airspace monitoring and incident management**. Its first release focuses on combining observations from authorized sources into a clear operational picture for human operators.

> **Status:** v0.5.1 local beta prototype; simulation only, no live drone detection. Simulated observations only; there is no live drone detection.

## Quick start (local demo)

- Python 3.12+.
- Install dependencies: `python -m pip install -r requirements-dev.txt`.
- Run tests: `python -m pytest -q`.
- Start: `uvicorn aervigia.app:app --host 127.0.0.1 --port 8000`.
- Open: http://127.0.0.1:8000. API schema: http://127.0.0.1:8000/docs.

Or use `docker compose up --build`. See [local run guide](docs/RUN.md) for details.

By default, read-only access is available on localhost in compatibility mode.
To enable named accounts, provision users with `python -m aervigia.auth` and set
`AERVIGIA_USERS_FILE`; legacy shared keys are then ignored. Docker Compose
provides a local persistent SQLite journal with hourly retention sweeps.
See [local run guide](docs/RUN.md) for account provisioning and revocation.
**Do not expose this demo to the public Internet.**

## Current implementation (v0.5.1)

- Python/FastAPI and Pydantic-validated synthetic observation API.
- Self-contained responsive HTML/CSS/JavaScript dashboard with synthetic tracks.
- Two deterministic simulator sources and a fictional protected zone.
- Simulated incidents with pending → reviewed → closed workflow, unique public reference, filters and event history.
- Individual JSON reports and operator-restricted bulk JSON/CSV exports for the **latest 80 incidents** in the current simulation.
- Three selectable, deterministic synthetic scenarios with admin-controlled start, pause and resume. Scenario selection is journaled; pause is local/ephemeral.
- Safe scenario switching in the dashboard: explicit confirmation and atomic protection against stale runs from other admin sessions.
- Only reviewed incidents may be closed; authorized operator identities are recorded.
- Optional persistent SQLite event journal with replay and startup retention (1–30 days).
- Optional named viewer/operator/admin accounts with revocable personal bearer tokens and per-user audit attribution.
- Legacy local shared keys remain available only when the named-user registry is disabled.
- No multi-sensor fusion or real equipment.
- Automated unit/API tests in GitHub Actions.

## Product goals

- Ingest authorized observations from Remote ID-compatible receivers and simulated sensors.
- Normalize incoming observations into a versioned, vendor-independent model.
- Correlate observations into tracks without overstating identification certainty.
- Visualize tracks and sensor provenance on a real-time map.
- Configure protected zones, authorized flights and human-reviewed alerts.
- Maintain an auditable incident history with appropriate retention controls.

## MVP scope — initial v0.1 baseline

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

## Technology direction

- API: Python + FastAPI, typed schemas.
- Web dashboard: dependency-free HTML/CSS/JS for the demo; Next.js/TypeScript may follow only if justified.
- Data: SQLite event journal for the local demo, with ongoing expiry, or memory-only if not configured. PostgreSQL/PostGIS remains deferred.
- Local development: Docker Compose.
- Testing: synthetic event fixtures with deterministic trajectories.

The first prototype is deliberately minimal to validate UX and event handling before adding complexity.

## Roadmap

- [x] Define synthetic observation schema and deterministic simulator
- [x] Implement an authenticated-write ingestion API with validation
- [x] Build a simulated track dashboard
- [x] Add a hard-coded demo zone and human-reviewed, in-memory alerts
- [x] Validate automated tests and JavaScript syntax in CI
- [x] Add SQLite journal, restart replay and startup plus continuous retention
- [x] Add local viewer/operator keys and an audit endpoint for operator actions
- [x] Validate responsive layout and keyboard alert actions with Chromium browser tests
- [ ] Review the final visual design manually (screenshots generated in PR CI)
- [x] Add named-account roles, revocable personal tokens and runtime retention sweeps
- [x] Add pending/reviewed/closed incident workflow and recent-history filter
- [x] Add simulation-only incident reports and safe bounded JSON/CSV downloads
- [x] Add three preconfigured, fully synthetic simulation scenarios and admin controls
- [ ] Add external identity integration, session expiry, MFA and production-grade security
- [ ] Evaluate multi-sensor integrations after safety and legal review

## License and ownership

Copyright (c) 2026 **Eduardo Yauri**. All rights reserved.

AERVIGIA is **publicly viewable but not open-source**. Use, redistribution,
modification or commercial deployment requires written authorization.
See [LICENSE](LICENSE) for the full terms.

**Copyright holder:** Eduardo Yauri · **GitHub account:** Emmakex · **Project:** AERVIGIA
