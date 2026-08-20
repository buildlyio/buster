from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentRuntime(BaseModel):
    id: str = ""
    runtime_type: str = "hermes"
    name: str = ""
    executable: str = ""
    argv_template: list[str] = Field(default_factory=list)
    allowed_task_kinds: list[str] = Field(default_factory=list)
    api_key_env: str = ""


class AgentModeConfig(BaseModel):
    mode: Literal["single", "split", "delegate"] = "single"
    specialist_overrides: dict[str, str] = Field(default_factory=dict)
    runtimes: list[AgentRuntime] = Field(default_factory=list)


class SpecialistOverride(BaseModel):
    role: str
    model: str = ""
    kind: str = ""


class RuntimeManifest(BaseModel):
    runtime_type: str = ""
    executable: str = ""
    argv_template: list[str] = Field(default_factory=list)
