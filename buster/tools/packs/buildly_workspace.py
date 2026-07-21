"""Buildly Workspace tool pack (mock-backed in Phase 1)."""

from __future__ import annotations

from pydantic import BaseModel

from buster.buildly import get_buildly_adapter
from buster.tools.registry import tool


class Empty(BaseModel):
    pass


class ProductsResult(BaseModel):
    products: list[dict]


@tool(
    id="buildly.products",
    description="List Buildly Workspace products (mock data in Phase 1).",
    pack="buildly_workspace",
    permission="read",
)
async def products(_: Empty | None = None) -> ProductsResult:
    adapter = get_buildly_adapter()
    items = await adapter.products()
    return ProductsResult(products=[p.model_dump() for p in items])


class OpportunitiesResult(BaseModel):
    opportunities: list[dict]


@tool(
    id="buildly.opportunities",
    description="List Buildly opportunities (mock CollabHub data in Phase 1).",
    pack="buildly_workspace",
    permission="read",
)
async def opportunities(_: Empty | None = None) -> OpportunitiesResult:
    adapter = get_buildly_adapter()
    items = await adapter.opportunities()
    return OpportunitiesResult(opportunities=[o.model_dump() for o in items])
