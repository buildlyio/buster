"""FastAPI app: Core REST API + SSE event stream + web UI mount.

Binds to localhost by default (see config). LAN access requires explicit
onboarding approval and a token (enforced by a dependency when enabled).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from buster import __version__ as buster_version
from buster.api.routes import router as api_router
from buster.config import load_config
from buster.discovery.advertise import start_advertising_async, stop_advertising_async
from buster.scheduler import get_alerts
from buster.scheduler.service import Scheduler
from buster.voice.notifier import VoiceNotifier
from buster.web import mount_web


@asynccontextmanager
async def _lifespan(app: FastAPI):
    scheduler = Scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    # Voice notifier: speak configured events + emit voice.announce for the web.
    notifier = VoiceNotifier()
    notifier.start()
    app.state.voice_notifier = notifier
    # Advertise buster.local on the LAN (best-effort; localhost always works).
    await start_advertising_async()
    # Background update-checker: periodically call GitHub and raise an alert
    # if a newer release is available.
    async def _update_loop():
        from buster.updates import check_for_update
        try:
            while True:
                try:
                    info = await check_for_update()
                    if info.get("available"):
                        get_alerts().raise_alert(
                            code="update_available",
                            title=f"Buster update available: {info.get('latest')}",
                            severity="warning",
                            detail=f"{info.get('current')} → {info.get('latest')}",
                        )
                    else:
                        get_alerts().resolve("update_available")
                except Exception:
                    # network errors are non-fatal; try again later
                    pass
                await asyncio.sleep(6 * 3600)
        except asyncio.CancelledError:
            return
    app.state._update_task = asyncio.create_task(_update_loop())
    try:
        yield
    finally:
        await scheduler.stop()
        await notifier.stop()
        await stop_advertising_async()
        # Cancel background update checker
        if hasattr(app.state, "_update_task"):
            app.state._update_task.cancel()
            try:
                await app.state._update_task
            except Exception:
                pass


def create_app() -> FastAPI:
    config = load_config()
    app = FastAPI(title="Buster Core", version=buster_version, lifespan=_lifespan)
    app.state.config = config
    app.include_router(api_router, prefix="/api")
    mount_web(app)
    return app
