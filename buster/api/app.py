"""FastAPI app: Core REST API + SSE event stream + web UI mount.

Binds to localhost by default (see config). LAN access requires explicit
onboarding approval and a token (enforced by a dependency when enabled).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from buster.api.routes import router as api_router
from buster.config import load_config
from buster.discovery.advertise import start_advertising_async, stop_advertising_async
from buster.scheduler.service import Scheduler
from buster.web import mount_web


@asynccontextmanager
async def _lifespan(app: FastAPI):
    scheduler = Scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    # Advertise buster.local on the LAN (best-effort; localhost always works).
    await start_advertising_async()
    try:
        yield
    finally:
        await scheduler.stop()
        await stop_advertising_async()


def create_app() -> FastAPI:
    config = load_config()
    app = FastAPI(title="Buster Core", version="0.1.0", lifespan=_lifespan)
    app.state.config = config
    app.include_router(api_router, prefix="/api")
    mount_web(app)
    return app
