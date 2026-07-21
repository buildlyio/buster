"""Discovery tool pack: probe configured URLs, list services/nodes.

Read-only. Trust decisions are made by the user, never by tools.
"""

from __future__ import annotations

from pydantic import BaseModel

from buster.config import load_config
from buster.discovery import get_discovery
from buster.tools.registry import tool


class Empty(BaseModel):
    pass


class DiscoverResult(BaseModel):
    services: list[dict]
    nodes: list[dict]


@tool(
    id="discovery.scan",
    description="Probe configured service URLs for LCDP manifests (read-only).",
    pack="discovery",
    permission="network",
    network_access=True,
)
async def scan(_: Empty | None = None) -> DiscoverResult:
    config = load_config()
    disco = get_discovery()
    for url in config.discovery.service_urls:
        await disco.probe_url(url)
    return DiscoverResult(services=disco.list_services(), nodes=disco.list_nodes())


class ListResult(BaseModel):
    services: list[dict]
    nodes: list[dict]


@tool(
    id="discovery.list",
    description="List discovered services and Buster nodes with trust status.",
    pack="discovery",
    permission="read",
)
async def list_discovered(_: Empty | None = None) -> ListResult:
    disco = get_discovery()
    return ListResult(services=disco.list_services(), nodes=disco.list_nodes())
