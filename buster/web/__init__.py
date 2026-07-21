"""Local web interface (FastAPI + Jinja + HTMX, precompiled assets, no Node)."""

from buster.web.mount import mount_web

__all__ = ["mount_web"]
