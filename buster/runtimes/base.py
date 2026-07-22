"""Runtime adapter interface + typed records.

Adapters expose whatever a runtime *safely* supports, preferring, in order:
official API → MCP → LCDP → supported CLI subprocess → read-only process
discovery. Submitting executable tasks to real external runtimes is disabled by
default. No credentials, memory, history, permissions, schedules, nodes, or API
keys are ever imported automatically.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field


class RuntimeStatus(str, Enum):
    DETECTED = "detected"
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class RuntimeTask(BaseModel):
    """A bounded task to hand to an external runtime. Data in, data out.

    Deliberately minimal: a prompt and limits. No shell strings, no file paths
    the runtime could abuse, no Buster credentials or permissions.
    """

    prompt: str
    timeout_s: int = 120
    max_output_bytes: int = 200_000
    # Opaque, read-only context strings the caller chooses to share.
    context: list[str] = Field(default_factory=list)


class RuntimeRun(BaseModel):
    run_id: str
    runtime_id: str
    status: RunStatus = RunStatus.QUEUED
    # Result is DATA ONLY. It can never cause Buster to auto-execute an action.
    output: str = ""
    error: str = ""
    # Provenance for the audit trail / event stream.
    executing_runtime: str = ""
    model: str = ""
    inference_location: str = "unknown"
    external_data_shared: bool = False


class RuntimeInfo(BaseModel):
    id: str
    runtime_type: str                 # buster | hermes | openclaw | mcp | cli
    name: str
    detected_via: str = ""            # api | mcp | lcdp | cli | process
    status: RuntimeStatus = RuntimeStatus.DETECTED
    version: str = ""
    models: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    schedules: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    trust: str = "detected"
    task_submission_enabled: bool = False


class RuntimeAdapter(Protocol):
    runtime_type: str

    async def detect(self) -> RuntimeInfo | None: ...
    async def health(self, info: RuntimeInfo) -> RuntimeStatus: ...
    async def capabilities(self, info: RuntimeInfo) -> list[str]: ...


class TaskCapableAdapter(RuntimeAdapter, Protocol):
    """Adapter that additionally supports bounded task submission.

    A delegated run returns DATA ONLY. Its result must never cause Buster to
    execute a system-changing action automatically. Streamed lines are progress
    text, never Buster tool calls.
    """

    async def submit(self, task: RuntimeTask) -> RuntimeRun: ...
    async def stream(self, run_id: str) -> AsyncIterator[str]: ...
    async def cancel(self, run_id: str) -> None: ...
    async def logs(self, run_id: str, limit: int = 100) -> list[str]: ...
