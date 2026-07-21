"""Tool specification: metadata attached to every registered tool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    id: str
    name: str
    description: str
    pack: str = "core"
    permission: str = "read"        # read | system.read | system.write | ...
    risk_level: int = 0             # 0..3 (see permissions module)
    platforms: list[str] = Field(default_factory=lambda: ["macos", "linux"])
    required_commands: list[str] = Field(default_factory=list)
    timeout_seconds: int = 30
    network_access: bool = False
    untrusted_output: bool = False  # output may contain untrusted content
    requires_confirmation: bool = False

    # runtime-only fields (not serialized in DB)
    input_model: type[BaseModel] | None = Field(default=None, exclude=True)
    output_model: type[BaseModel] | None = Field(default=None, exclude=True)
    func: Callable[..., Awaitable[Any]] | None = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    def supported_here(self, platform: str) -> bool:
        return platform in self.platforms
