"""Runtime adapters: Buster (self), mock Hermes/OpenClaw, generic CLI.

Real read-only detection is attempted first (process/CLI presence). If a
runtime isn't present, the mock adapters still return representative records so
the CLI/web Agents section is populated for demos and tests.
"""

from __future__ import annotations

import shutil

from buster import __version__
from buster.runtimes.base import RuntimeInfo, RuntimeStatus


class BusterSelfAdapter:
    runtime_type = "buster"

    async def detect(self) -> RuntimeInfo:
        return RuntimeInfo(
            id="runtime.buster.self",
            runtime_type="buster",
            name="Buster (this node)",
            detected_via="api",
            status=RuntimeStatus.RUNNING,
            version=__version__,
            capabilities=["research", "diagnostics", "discovery", "reports"],
            trust="administrative",
        )


class HermesAdapter:
    runtime_type = "hermes"

    async def detect(self) -> RuntimeInfo:
        present = shutil.which("hermes") is not None
        return RuntimeInfo(
            id="runtime.hermes",
            runtime_type="hermes",
            name="Hermes",
            detected_via="cli" if present else "mock",
            status=RuntimeStatus.DETECTED if present else RuntimeStatus.UNKNOWN,
            capabilities=["chat", "skills", "schedules"],
            skills=["daily-brief"],
            channels=["cli"],
            trust="detected",
            task_submission_enabled=False,
        )


class OpenClawAdapter:
    runtime_type = "openclaw"

    async def detect(self) -> RuntimeInfo:
        present = shutil.which("openclaw") is not None
        return RuntimeInfo(
            id="runtime.openclaw",
            runtime_type="openclaw",
            name="OpenClaw",
            detected_via="cli" if present else "mock",
            status=RuntimeStatus.DETECTED if present else RuntimeStatus.UNKNOWN,
            capabilities=["automation", "tasks"],
            channels=["cli"],
            trust="detected",
            task_submission_enabled=False,
        )
