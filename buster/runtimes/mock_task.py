"""Mock task-capable adapter for Hermes/OpenClaw demos and tests.

Returns deterministic, data-only output. Used when the real runtime isn't
present so the Agents section and tests exercise the full submit/stream/cancel
path without any external dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from buster.runtimes.base import RunStatus, RuntimeRun, RuntimeTask


class MockTaskAdapter:
    def __init__(self, runtime_id: str, name: str) -> None:
        self.id = runtime_id
        self.name = name
        self._runs: dict[str, RuntimeRun] = {}

    async def submit(self, task: RuntimeTask) -> RuntimeRun:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        # Deterministic, clearly-labelled mock result. DATA ONLY.
        output = (
            f"[mock:{self.name}] received task ({len(task.prompt)} chars). "
            "This is simulated output; no real runtime executed."
        )
        run = RuntimeRun(
            run_id=run_id, runtime_id=self.id, status=RunStatus.COMPLETED,
            output=output, executing_runtime=self.name, model="mock",
            inference_location="device", external_data_shared=False,
        )
        self._runs[run_id] = run
        return run

    async def stream(self, run_id: str) -> AsyncIterator[str]:
        run = self._runs.get(run_id)
        if run:
            for line in run.output.splitlines() or [run.output]:
                yield line

    async def cancel(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run and run.status == RunStatus.RUNNING:
            run.status = RunStatus.CANCELLED

    async def logs(self, run_id: str, limit: int = 100) -> list[str]:
        run = self._runs.get(run_id)
        return (run.output.splitlines() if run else [])[-limit:]
