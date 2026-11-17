# AERVIGIA — Preliminary Architecture

## Guiding choice

Build a vendor-neutral, simulation-first **passive airspace awareness** application. Avoid manufacturer lock-in and do not introduce live sensing integrations before product validation.

## Logical services

1. **Simulator / adapter interface:** deterministic synthetic observations first; future adapters must document legal authorization, provenance, timestamps and uncertainty.
2. **Ingestion API:** authenticated, schema-validated requests; replay protection and bounded payload size.
3. **Normalizer:** converts device-specific messages into a canonical observation record; never guesses missing information.
4. **Correlation and tracks:** maintains provisional identifiers and last-seen states. Must expose confidence and limitations, and handle duplicate/out-of-order events.
5. **Rules and zones:** configurable polygon boundaries and transparent alert rules without autonomous actions.
6. **API/UI:** maps, operator review workflow, event timelines and filters.
7. **Storage and audit:** observations, track updates, incident records and administrative actions with configurable retention.

## Proposed stack

- Backend: FastAPI / Python, typed schemas and migrations.
- Frontend: Next.js / TypeScript, accessible interface and map component.
- Database: PostgreSQL + PostGIS.
- Local orchestration: Docker Compose.
- Quality: schema tests, contract tests, fixture-driven simulation, security lint and CI.

## Canonical observation (illustrative only)

```json
{
  "schema_version": "0.1",
  "observation_id": "obs-sim-001",
  "source_id": "simulator-a",
  "source_type": "simulator",
  "observed_at": "2026-11-17T10:00:00Z",
  "position": {
    "latitude": 41.0,
    "longitude": 2.0,
    "altitude_m": 120.0
  },
  "position_uncertainty_m": 20.0,
  "classification": "unknown",
  "simulation": true
}
```

This fixture illustrates the message contract, **not a real-world measurement**. Position, classification and uncertainty may be unavailable in live inputs; schema evolution must support this.

## Security, privacy and safety

- Require authenticated ingestion and role-appropriate UI access.
- Use HTTPS for external connections, restrict CORS and audit privileged changes.
- Keep secrets and raw sensitive observations out of Git.
- Document retention, export/delete procedures and applicable privacy obligations.
- Isolate demo/simulation from future production sensor integration.
- All alerts inform an authorized human operator; no weapon or mitigation control endpoints.

## Development sequence

Phase 0: schema + synthetic fixtures → Phase 1: authenticated API → Phase 2: map and tracks → Phase 3: zone alert and audit. Hardware connectors are explicitly deferred.
