"""Network diagnostics tool pack (read-only, risk level 0)."""

from __future__ import annotations

import socket

from pydantic import BaseModel

from buster.diagnostics.network import run_network_check
from buster.tools.registry import tool


class Empty(BaseModel):
    pass


class NetworkCheckResult(BaseModel):
    checks: list[dict]


@tool(
    id="network.check",
    description="Run read-only network health checks (interfaces, DNS, internet, Ollama).",
    pack="network_diagnostics",
    permission="system.read",
    risk_level=0,
    network_access=True,
)
async def network_check(_: Empty | None = None) -> NetworkCheckResult:
    results = await run_network_check()
    return NetworkCheckResult(checks=[r.model_dump() for r in results])


class ResolveArgs(BaseModel):
    host: str


class ResolveResult(BaseModel):
    host: str
    addresses: list[str]
    resolved: bool


@tool(
    id="network.resolve_dns",
    description="Resolve a hostname to IP addresses.",
    pack="network_diagnostics",
    permission="system.read",
    risk_level=0,
    network_access=True,
    timeout_seconds=10,
)
async def resolve_dns(args: ResolveArgs) -> ResolveResult:
    try:
        infos = socket.getaddrinfo(args.host, None)
        addrs = sorted({i[4][0] for i in infos})
        return ResolveResult(host=args.host, addresses=addrs, resolved=True)
    except OSError:
        return ResolveResult(host=args.host, addresses=[], resolved=False)
