"""Runtime adapter interface + typed records.

Adapters expose whatever a runtime *safely* supports, preferring, in order:
official API → MCP → LCDP → supported CLI subprocess → read-only process
discovery. Submitting executable tasks to real external runtimes is disabled by
default. No credentials, memory, history, permissions, schedules, nodes, or API
keys are ever imported automatically.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field


class RuntimeStatus(str, Enum):
    DETECTED = "detected"
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


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
