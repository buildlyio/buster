"""Microservice / Buildly-module scaffolding.

Native Python code generation (MIT). Inspired by the Buildly CLI workflow but
written from scratch — no GPL code is copied. Produces a FastAPI + SQLAlchemy
module with CRUD routes from a list of model names, plus run/Docker files.

Lightweight: pure string templates, no heavy templating engine, offline.
"""

from buster.scaffold.forge import ForgeResult, adapt_to_marketplace, new_forge_app
from buster.scaffold.generator import ScaffoldPlan, ScaffoldResult, scaffold_fastapi_module

__all__ = [
    "ScaffoldPlan",
    "ScaffoldResult",
    "scaffold_fastapi_module",
    "ForgeResult",
    "adapt_to_marketplace",
    "new_forge_app",
]
