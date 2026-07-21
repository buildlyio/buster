"""System diagnostics tool pack (read-only, risk level 0)."""

from __future__ import annotations

from pydantic import BaseModel

from buster.diagnostics.system import run_system_check
from buster.tools.registry import tool


class Empty(BaseModel):
    pass


class SystemCheckResult(BaseModel):
    checks: list[dict]


@tool(
    id="system.check",
    description="Run read-only system health checks (CPU, memory, disk, Ollama, ...).",
    pack="system_diagnostics",
    permission="system.read",
    risk_level=0,
)
async def system_check(_: Empty | None = None) -> SystemCheckResult:
    results = run_system_check()
    return SystemCheckResult(checks=[r.model_dump() for r in results])


class ProcessesArgs(BaseModel):
    limit: int = 20


class ProcessList(BaseModel):
    processes: list[dict]


@tool(
    id="system.processes",
    description="List high-resource processes.",
    pack="system_diagnostics",
    permission="system.read",
    risk_level=0,
    timeout_seconds=10,
)
async def list_processes(args: ProcessesArgs) -> ProcessList:
    from buster.diagnostics.common import top_processes

    res = top_processes(limit=args.limit)
    return ProcessList(processes=res.evidence.get("processes", []))
