"""Bounded agent loop.

Steps: receive input → classify → build context → select tools → select model →
request response/tool call → validate tool calls → check permissions → execute
approved tools → return results → repeat to a step limit → final response.

Safety: the model never gets raw shell. Tool calls are validated against typed
schemas. Level-0 tools run automatically; level ≥2 tools require confirmation
(surfaced as a permission request; in Phase 1 auto-run tools are read-only).
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from buster.agent.tasks import get_task_store
from buster.config import load_config
from buster.context import build_context
from buster.events import Event, EventType, get_event_bus
from buster.models.provider import ChatMessage, ChatRequest
from buster.models.router import ModelRouter
from buster.permissions import RiskLevel, audit
from buster.tools import get_registry
from buster.tools.spec import ToolSpec


class AgentResult(BaseModel):
    content: str
    model: str
    provider: str
    inference_location: str
    external_data_shared: bool
    task_id: str
    steps: int
    tools_used: list[str] = []


def _classify(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ("research", "compare", "sources", "find out about")):
        return "research"
    if any(w in low for w in ("cpu", "memory", "disk", "system", "process")):
        return "diagnostic"
    if any(w in low for w in ("network", "dns", "ping", "gateway", "ollama")):
        return "diagnostic"
    return "chat"


def _tools_for_task(kind: str, platform: str, registry) -> list[ToolSpec]:
    """Select a limited, relevant subset of tools (read-only auto-run in Phase 1)."""
    all_tools = [t for t in registry.for_platform(platform) if t.risk_level <= RiskLevel.SAFE_BUSTER]
    if kind == "research":
        packs = {"web_research", "report_builder", "memory", "core"}
    elif kind == "diagnostic":
        packs = {"system_diagnostics", "network_diagnostics", "core"}
    else:
        packs = {"memory", "core", "system_diagnostics"}
    return [t for t in all_tools if t.pack in packs]


# Tool JSON-schemas are stable per tool id; cache them so we don't rebuild the
# Ollama tool payload on every request.
_SCHEMA_CACHE: dict[str, dict] = {}


def _to_ollama_tools(specs: list[ToolSpec]) -> list[dict]:
    out = []
    for s in specs:
        cached = _SCHEMA_CACHE.get(s.id)
        if cached is None:
            schema = (
                s.input_model.model_json_schema()
                if s.input_model
                else {"type": "object", "properties": {}}
            )
            cached = {
                "type": "function",
                "function": {"name": s.id, "description": s.description, "parameters": schema},
            }
            _SCHEMA_CACHE[s.id] = cached
        out.append(cached)
    return out


async def _delegate_subtask(prompt: str, kind: str, config) -> AgentResult | None:
    """Delegate the task to a configured external runtime iff policy allows.

    Returns None when delegation is not possible or safe, so the caller falls
    back to the normal local LLM path. In Phase 1 this path is limited to
    non-external adapters/mock runtimes; real external execution requires
    explicit approval outside the agent loop.
    """
    from buster.runtimes.service import RuntimeSubmissionError, get_runtime_service
    from buster.runtimes.base import RuntimeTask

    mode = str(getattr(getattr(config, "agent", None), "mode", "single") or "single").strip().lower()
    if mode != "delegate":
        return None

    service = get_runtime_service()
    candidates = []
    raw_runtimes = getattr(getattr(config, "agent", None), "runtimes", []) or []
    for rt in raw_runtimes:
        rid = str(getattr(rt, "id", "") or "").strip()
        if not rid:
            continue
        row = service._row(rid)
        if not row:
            continue
        allowed = [str(x).strip() for x in (row.get("allowed_task_kinds") or []) if str(x).strip()]
        if kind in allowed:
            candidates.append(rid)

    if not candidates:
        return None

    runtime_id = candidates[0]
    task = RuntimeTask(
        prompt=prompt,
        timeout_s=int(getattr(config.inference, "tool_timeout_seconds", 120) or 120),
    )
    try:
        await service.request_submission(runtime_id, task)
    except RuntimeSubmissionError:
        return None

    try:
        run = await service.submit(runtime_id, task)
    except Exception:  # noqa: BLE001
        return None

    output = str(run.output or "").strip() or "Subtask completed with no output."
    return AgentResult(
        content=output,
        model=str(run.model or "delegated"),
        provider=str(runtime_id),
        inference_location=str(run.inference_location or "external"),
        external_data_shared=bool(run.external_data_shared),
        task_id="",
        steps=1,
        tools_used=[],
    )


class Agent:
    def __init__(self) -> None:
        self.config = load_config()
        self.router = ModelRouter(self.config)
        self.registry = get_registry()

    async def run(self, prompt: str, conversation_id: str | None = None, workspace: str = "default") -> AgentResult:
        from buster.models.capability import detect_capabilities

        bus = get_event_bus()
        store = get_task_store()
        kind = _classify(prompt)
        task = store.create_task(kind=kind, title=prompt[:80], workspace=workspace)
        await bus.publish(Event(type=EventType.TASK_CREATED, task_id=task.id, title=task.title,
                                metadata={"kind": kind}))
        store.set_status(task.id, "running")
        await bus.publish(Event(type=EventType.TASK_STARTED, task_id=task.id, title=task.title))

        # Optional specialization/runtime handoff before local loop.
        delegated = await _delegate_subtask(prompt, kind, self.config)
        if delegated is not None:
            store.set_status(task.id, "completed")
            await bus.publish(Event(type=EventType.TASK_COMPLETED, task_id=task.id,
                                    metadata={"tools_used": delegated.tools_used, "steps": delegated.steps,
                                              "delegated": True}))
            audit(category="runtime", task_id=task.id,
                  detail={"delegated": True, "runtime_id": delegated.provider},
                  result="completed", model=delegated.model,
                  inference_location=delegated.inference_location,
                  external_data_shared=delegated.external_data_shared)
            if conversation_id:
                store.add_message(conversation_id, "user", prompt)
                store.add_message(conversation_id, "assistant", delegated.content,
                                  metadata={"model": delegated.model, "location": delegated.inference_location,
                                            "delegated": True})
            return AgentResult(
                content=delegated.content,
                model=delegated.model,
                provider=delegated.provider,
                inference_location=delegated.inference_location,
                external_data_shared=delegated.external_data_shared,
                task_id=task.id,
                steps=delegated.steps,
                tools_used=delegated.tools_used,
            )

        # Context
        ctx = build_context(prompt)
        await bus.publish(Event(type=EventType.CONTEXT_LOADED, task_id=task.id,
                                metadata={"categories": ctx.categories_loaded,
                                          "tokens": ctx.token_estimate}))

        # Model
        decision = await self.router.route(estimated_tokens=ctx.token_estimate)
        await bus.publish(Event(type=EventType.MODEL_SELECTED, task_id=task.id,
                                title=f"{decision.provider.name}:{decision.model}",
                                metadata={"provider": decision.provider.name, "model": decision.model,
                                          "location": decision.location, "reason": decision.reason}))

        platform = detect_capabilities().platform
        tools = _tools_for_task(kind, platform, self.registry)

        messages = [ChatMessage(role="system", content=ctx.system_preamble)]
        for snip in ctx.memory_snippets:
            messages.append(ChatMessage(role="system", content=snip))
        messages.append(ChatMessage(role="user", content=prompt))

        tools_used: list[str] = []
        steps = 0
        final_content = ""

        provider = decision.provider
        supports_tools = decision.model != "none" and hasattr(provider, "chat")

        for steps in range(1, self.config.inference.max_steps + 1):
            req = ChatRequest(
                model=decision.model,
                messages=messages,
                tools=_to_ollama_tools(tools) if (tools and supports_tools) else None,
            )
            resp = await provider.chat(req)

            if resp.tool_calls:
                for tc in resp.tool_calls:
                    spec = self.registry.get(tc.name)
                    if spec is None:
                        messages.append(ChatMessage(role="tool", content=f"Unknown tool: {tc.name}"))
                        continue
                    # Permission check: only auto-run read-only / safe tools.
                    if spec.risk_level > RiskLevel.SAFE_BUSTER:
                        messages.append(ChatMessage(
                            role="tool",
                            content=f"Tool {tc.name} requires confirmation (risk {spec.risk_level}); skipped.",
                        ))
                        continue
                    await bus.publish(Event(type=EventType.TOOL_STARTED, task_id=task.id,
                                            tool=tc.name, title=spec.name, metadata=tc.arguments))
                    try:
                        result = await self.registry.invoke(tc.name, tc.arguments)
                        payload = result.model_dump() if isinstance(result, BaseModel) else result
                        tools_used.append(tc.name)
                        # Untrusted-content label for tool output.
                        wrapper = {"tool": tc.name, "untrusted": spec.untrusted_output, "result": payload}
                        messages.append(ChatMessage(role="tool", content=json.dumps(wrapper)[:8000]))
                        await bus.publish(Event(type=EventType.TOOL_COMPLETED, task_id=task.id,
                                                tool=tc.name, title=spec.name))
                        audit(category="tool", detail={"tool": tc.name}, task_id=task.id,
                              risk_level=spec.risk_level, result="ok", model=decision.model,
                              inference_location=decision.location)
                    except Exception as exc:  # noqa: BLE001
                        messages.append(ChatMessage(role="tool", content=f"Tool error: {exc}"))
                        await bus.publish(Event(type=EventType.TOOL_FAILED, task_id=task.id,
                                                tool=tc.name, title=str(exc)))
                continue  # let the model incorporate tool results

            final_content = resp.content
            break

        store.set_status(task.id, "completed")
        await bus.publish(Event(type=EventType.TASK_COMPLETED, task_id=task.id,
                                metadata={"tools_used": tools_used, "steps": steps}))
        audit(category="model", detail={"kind": kind}, task_id=task.id, result="completed",
              model=decision.model, inference_location=decision.location,
              external_data_shared=decision.external_data_shared)

        if conversation_id:
            store.add_message(conversation_id, "user", prompt)
            store.add_message(conversation_id, "assistant", final_content,
                              metadata={"model": decision.model, "location": decision.location})

        return AgentResult(
            content=final_content, model=decision.model, provider=decision.provider.name,
            inference_location=decision.location, external_data_shared=decision.external_data_shared,
            task_id=task.id, steps=steps, tools_used=tools_used,
        )
