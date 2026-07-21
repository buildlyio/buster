"""Global tool registry + @tool decorator.

Tools are async functions with typed input/output. The decorator captures
metadata; the registry validates arguments against the input model before the
tool runs. The model never gets raw shell access — only these typed tools.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from buster.tools.spec import ToolSpec

# Tool packs shipped in Phase 1. Imported lazily by the registry.
_BUILTIN_PACKS = [
    "buster.tools.packs.core",
    "buster.tools.packs.files",
    "buster.tools.packs.system_diagnostics",
    "buster.tools.packs.network_diagnostics",
    "buster.tools.packs.web_research",
    "buster.tools.packs.report_builder",
    "buster.tools.packs.memory",
    "buster.tools.packs.tasks",
    "buster.tools.packs.discovery",
    "buster.tools.packs.buildly_workspace",
]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.id in self._tools:
            raise ValueError(f"Duplicate tool id: {spec.id}")
        self._tools[spec.id] = spec

    def get(self, tool_id: str) -> ToolSpec | None:
        return self._tools.get(tool_id)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def packs(self) -> set[str]:
        return {t.pack for t in self._tools.values()}

    def for_platform(self, platform: str) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.supported_here(platform)]

    async def invoke(self, tool_id: str, arguments: dict[str, Any]) -> BaseModel | dict:
        spec = self._tools.get(tool_id)
        if spec is None or spec.func is None:
            raise KeyError(f"Unknown tool: {tool_id}")
        # Validate arguments against the typed input model.
        if spec.input_model is not None:
            parsed = spec.input_model.model_validate(arguments)
            kwargs = parsed.model_dump()
        else:
            kwargs = arguments
        return await spec.func(**kwargs)


_PENDING: list[ToolSpec] = []


def tool(
    *,
    id: str,
    description: str,
    name: str | None = None,
    pack: str = "core",
    permission: str = "read",
    risk_level: int = 0,
    platforms: list[str] | None = None,
    required_commands: list[str] | None = None,
    timeout_seconds: int = 30,
    network_access: bool = False,
    untrusted_output: bool = False,
    requires_confirmation: bool = False,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Register an async function as a Buster tool.

    Input/output models are inferred from the signature: the first parameter
    annotated with a Pydantic model becomes the input schema; the return
    annotation (if a Pydantic model) becomes the output schema.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        sig = inspect.signature(func)
        input_model = None
        for p in sig.parameters.values():
            ann = p.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                input_model = ann
                break
        ret = sig.return_annotation
        output_model = ret if isinstance(ret, type) and issubclass(ret, BaseModel) else None

        spec = ToolSpec(
            id=id,
            name=name or id,
            description=description,
            pack=pack,
            permission=permission,
            risk_level=risk_level,
            platforms=platforms or ["macos", "linux"],
            required_commands=required_commands or [],
            timeout_seconds=timeout_seconds,
            network_access=network_access,
            untrusted_output=untrusted_output,
            requires_confirmation=requires_confirmation,
            input_model=input_model,
            output_model=output_model,
            func=func,
        )
        _PENDING.append(spec)
        func.__tool_spec__ = spec  # type: ignore[attr-defined]
        return func

    return decorator


@lru_cache(maxsize=1)
def get_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for module in _BUILTIN_PACKS:
        try:
            importlib.import_module(module)
        except Exception:  # noqa: BLE001
            # A pack that fails to import shouldn't take down the whole registry.
            continue
    for spec in _PENDING:
        if reg.get(spec.id) is None:
            reg.register(spec)
    return reg
