"""AERVIGIA FastAPI backend and local synthetic demo."""

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from aervigia import __version__
from aervigia.auth import Identity, UserRegistry
from aervigia.core import Observation, TrackStore
from aervigia.storage import SQLiteEventJournal


def create_app(engine: TrackStore | None = None, background: bool = True) -> FastAPI:
    db_path = os.environ.get("AERVIGIA_DB_PATH", "").strip()
    owns_journal = engine is None and bool(db_path)
    journal = (
        SQLiteEventJournal(
            db_path, retention_days=int(os.environ.get("AERVIGIA_RETENTION_DAYS", "7"))
        )
        if owns_journal else None
    )
    store = engine if engine is not None else TrackStore(journal=journal)
    api_token = os.environ.get("AERVIGIA_API_TOKEN", "")
    view_token = os.environ.get("AERVIGIA_VIEW_TOKEN", "")
    operator_id = os.environ.get("AERVIGIA_OPERATOR_ID", "local-operator")
    users_file = os.environ.get("AERVIGIA_USERS_FILE", "").strip()
    registry = UserRegistry(users_file) if users_file else None
    sweep_seconds = int(os.environ.get("AERVIGIA_RETENTION_SWEEP_SECONDS", "3600"))
    if not 60 <= sweep_seconds <= 86400:
        raise ValueError("AERVIGIA_RETENTION_SWEEP_SECONDS must be between 60 and 86400")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        tasks = []
        if background:
            async def simulate():
                while True:
                    store.advance()
                    await asyncio.sleep(1.5)
            tasks.append(asyncio.create_task(simulate()))
        if store.journal is not None:
            async def maintain():
                while True:
                    await asyncio.sleep(sweep_seconds)
                    await asyncio.to_thread(store.maintain)

            tasks.append(asyncio.create_task(maintain()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if owns_journal and journal is not None:
                journal.close()

    application = FastAPI(
        title="AERVIGIA — Simulation API",
        version=__version__,
        description="Passive situational awareness demonstration. Synthetic data only.",
        lifespan=lifespan,
    )

    def authorize(
        required: str, authorization: str | None = None,
        view_candidate: str | None = None, write_candidate: str | None = None,
    ) -> Identity:
        # Named-user mode is strict: legacy shared keys NEVER bypass the registry.
        if registry is not None:
            try:
                principal = registry.authenticate(authorization)
            except PermissionError:
                raise HTTPException(status_code=401, detail="Personal bearer token required")
            except (OSError, ValueError):
                raise HTTPException(status_code=503, detail="User registry unavailable")
            allowed = {
                "viewer": {"viewer", "operator", "admin"},
                "operator": {"operator", "admin"},
                "admin": {"admin"},
            }
            if principal.role not in allowed[required]:
                raise HTTPException(status_code=403, detail="Insufficient role")
            return principal

        if required == "viewer":
            if (not view_token
                    or (view_candidate and hmac.compare_digest(view_candidate, view_token))
                    or (api_token and write_candidate
                        and hmac.compare_digest(write_candidate, api_token))):
                return Identity("local-demo", "viewer")
            raise HTTPException(status_code=401, detail="Valid viewer key required")
        if not api_token:
            raise HTTPException(status_code=503, detail="Writes disabled: AERVIGIA_API_TOKEN not configured")
        if not write_candidate or not hmac.compare_digest(write_candidate, api_token):
            raise HTTPException(status_code=401, detail="Invalid operator key")
        # Compatibility with v0.2; in this mode the configured actor is not verified.
        return Identity(operator_id, "admin")

    @application.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(Path(__file__).resolve().parent.parent / "web" / "index.html")

    @application.get("/api/auth-mode")
    async def auth_mode():
        return {
            "mode": "named" if registry is not None else "legacy",
            "notice": "Local development demo only",
        }

    @application.get("/api/me")
    async def whoami(
        authorization: str | None = Header(default=None),
        x_view_key: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ):
        principal = authorize("viewer", authorization, x_view_key, x_api_key)
        return {"user_id": principal.user_id, "role": principal.role}

    @application.get("/healthz")
    async def health():
        return {"status": "ok", "version": __version__, "mode": "simulation"}

    @application.get("/api/state")
    async def state(
        x_view_key: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        authorize("viewer", authorization, x_view_key, x_api_key)
        return store.snapshot()

    @application.get("/api/audit")
    async def audit(
        x_view_key: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        authorize("viewer", authorization, x_view_key, x_api_key)
        return {
            "simulation": True,
            "persistence": store.journal is not None,
            "actions": store.audit_actions(),
        }

    @application.post("/api/observations", status_code=201)
    async def submit_observation(
        observation: Observation,
        x_api_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        authorize("operator", authorization, write_candidate=x_api_key)
        if observation.observed_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="observed_at must include a timezone")
        return store.ingest(observation)

    @application.post("/api/alerts/{alert_id}/ack")
    async def acknowledge_alert(
        alert_id: str,
        x_api_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        principal = authorize("operator", authorization, write_candidate=x_api_key)
        if not store.acknowledge(alert_id, actor=principal.user_id):
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"id": alert_id, "acknowledged": True}

    @application.post("/api/simulation/reset")
    async def reset_simulation(
        x_api_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        principal = authorize("admin", authorization, write_candidate=x_api_key)
        store.reset(actor=principal.user_id)
        store.advance()
        return {"reset": True, "mode": "simulation"}

    return application


app = create_app()
