"""Generic CLI-subprocess runtime adapter.

Runs a supported external agent CLI as a bounded subprocess: fixed argv template
(no shell), the task prompt passed as a single argument or stdin, a hard timeout,
and an output-size cap. This is the real execution path for runtimes that expose
a CLI (and the basis for bb-code in Phase 2.3).

Safety:
  * No shell — argv only; the prompt is data, never interpolated into a command.
  * Timeout + output cap enforced.
  * Output is returned as DATA. Buster never parses it into tool calls or
    actions. A delegated run cannot trigger a system-changing action.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import AsyncIterator

from buster.runtimes.base import (
    RunStatus,
    RuntimeInfo,
    RuntimeRun,
    RuntimeStatus,
    RuntimeTask,
)


class CliRuntimeAdapter:
    """Drive an external agent via a supported CLI.

    argv_template: the fixed command, with the literal token "{prompt}" where the
    task prompt should be substituted as ONE argument (never split, never shelled).
    If no "{prompt}" token is present, the prompt is written to the process stdin.
    """

    runtime_type = "cli"

    def __init__(
        self,
        *,
        id: str,
        name: str,
        executable: str,
        argv_template: list[str],
        location: str = "device",
    ) -> None:
        self.id = id
        self.name = name
        self.executable = executable
        self.argv_template = argv_template
        self.location = location
        self._runs: dict[str, RuntimeRun] = {}
        self._buffers: dict[str, list[str]] = {}

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    async def detect(self) -> RuntimeInfo | None:
        present = self.available()
        return RuntimeInfo(
            id=self.id,
            runtime_type=self.runtime_type,
            name=self.name,
            detected_via="cli" if present else "mock",
            status=RuntimeStatus.DETECTED if present else RuntimeStatus.UNKNOWN,
            capabilities=["task.submit"] if present else [],
        )

    async def health(self, info: RuntimeInfo) -> RuntimeStatus:
        return RuntimeStatus.DETECTED if self.available() else RuntimeStatus.UNKNOWN

    async def capabilities(self, info: RuntimeInfo) -> list[str]:
        return ["task.submit"] if self.available() else []

    def _build_argv(self, prompt: str) -> tuple[list[str], bool]:
        """Return (argv, use_stdin). Prompt is substituted as one arg or via stdin."""
        argv = [self.executable]
        used = False
        for tok in self.argv_template:
            if tok == "{prompt}":
                argv.append(prompt)  # single argument — never shell-split
                used = True
            else:
                argv.append(tok)
        return argv, (not used)

    async def submit(self, task: RuntimeTask) -> RuntimeRun:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run = RuntimeRun(run_id=run_id, runtime_id=self.id, status=RunStatus.RUNNING,
                         executing_runtime=self.name, inference_location=self.location)
        self._runs[run_id] = run
        self._buffers[run_id] = []

        if not self.available():
            run.status = RunStatus.FAILED
            run.error = f"{self.executable} not found on PATH"
            return run

        argv, use_stdin = self._build_argv(task.prompt)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if use_stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdin_data = task.prompt.encode() if use_stdin else None
            out, _ = await asyncio.wait_for(proc.communicate(stdin_data), timeout=task.timeout_s)
            text = out.decode(errors="replace")[: task.max_output_bytes]
            self._buffers[run_id] = text.splitlines()
            run.output = text
            run.status = RunStatus.COMPLETED if proc.returncode == 0 else RunStatus.FAILED
            if proc.returncode != 0:
                run.error = f"exit code {proc.returncode}"
        except TimeoutError:
            run.status = RunStatus.TIMEOUT
            run.error = f"timed out after {task.timeout_s}s"
        except FileNotFoundError as exc:
            run.status = RunStatus.FAILED
            run.error = f"command not found: {exc}"
        except Exception as exc:  # noqa: BLE001
            run.status = RunStatus.FAILED
            run.error = str(exc)
        return run

    async def stream(self, run_id: str) -> AsyncIterator[str]:
        # This adapter runs to completion in submit(); stream replays buffered
        # lines. (A future streaming CLI adapter can yield live lines instead.)
        for line in self._buffers.get(run_id, []):
            yield line

    async def cancel(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run and run.status == RunStatus.RUNNING:
            run.status = RunStatus.CANCELLED

    async def logs(self, run_id: str, limit: int = 100) -> list[str]:
        return self._buffers.get(run_id, [])[-limit:]
