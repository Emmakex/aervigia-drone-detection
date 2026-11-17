"""AERVIGIA FastAPI backend and local synthetic demo."""

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from aervigia import __version__
from aervigia.core import Observation, TrackStore


def create_app(engine: TrackStore | None = None, background: bool = True) -> FastAPI:
    store = engine if engine is not None else TrackStore()
    api_token = os.environ.get("AERVIGIA_API_TOKEN", "")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if background:
            async def simulate():
                while True:
                    store.advance()
                    await asyncio.sleep(1.5)
            task = asyncio.create_task(simulate())
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    application = FastAPI(
        title="AERVIGIA — Simulation API",
        version=__version__,
        description="Passive situational awareness demonstration. Synthetic data only.",
        lifespan=lifespan,
    )

    def require_write_token(candidate: str | None):
        if not api_token:
            raise HTTPException(status_code=503, detail="Writes disabled: AERVIGIA_API_TOKEN not configured")
        if not candidate or not hmac.compare_digest(candidate, api_token):
            raise HTTPException(status_code=401, detail="Invalid API key")

    @application.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(Path(__file__).resolve().parent.parent / "web" / "index.html")

    @application.get("/healthz")
    async def health():
        return {"status": "ok", "version": __version__, "mode": "simulation"}

    @application.get("/api/state")
    async def state():
        return store.snapshot()

    @application.post("/api/observations", status_code=201)
    async def submit_observation(observation: Observation, x_api_key: str | None = Header(default=None)):
        require_write_token(x_api_key)
        if observation.observed_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="observed_at must include a timezone")
        return store.ingest(observation)

    @application.post("/api/alerts/{alert_id}/ack")
    async def acknowledge_alert(alert_id: str, x_api_key: str | None = Header(default=None)):
        require_write_token(x_api_key)
        if not store.acknowledge(alert_id):
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"id": alert_id, "acknowledged": True}

    @application.post("/api/simulation/reset")
    async def reset_simulation(x_api_key: str | None = Header(default=None)):
        require_write_token(x_api_key)
        store.reset()
        store.advance()
        return {"reset": True, "mode": "simulation"}

    return application


app = create_app()
