"""Mount the web UI onto the FastAPI app.

Assets are precompiled/self-contained (HTMX vendored, CSS inline via template).
The destination machine never needs Node.js.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_WEB_DIR = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

# The nav sections in order.
_SECTIONS = [
    ("chat", "Chat"),
    ("research", "Research"),
    ("reports", "Reports"),
    ("system", "System"),
    ("network", "Network"),
    ("actions", "Actions"),
    ("alerts", "Alerts"),
    ("memory", "Memory"),
    ("nodes", "Nodes"),
    ("agents", "Agents"),
    ("dev", "Dev"),
    ("tools", "Tools"),
    ("prompts", "Prompts"),
    ("settings", "Settings"),
]


def mount_web(app: FastAPI) -> None:
    static_dir = _WEB_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return _TEMPLATES.TemplateResponse(
            request, "index.html", {"sections": _SECTIONS, "active": "chat"}
        )

    @app.get("/ui/{section}", response_class=HTMLResponse)
    async def section(request: Request, section: str):
        valid = {s for s, _ in _SECTIONS}
        active = section if section in valid else "chat"
        return _TEMPLATES.TemplateResponse(
            request, "index.html", {"sections": _SECTIONS, "active": active}
        )
