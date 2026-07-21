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


def _to_ollama_tools(specs: list[ToolSpec]) -> list[dict]:
    out = []
    for s in specs:
        schema = s.input_model.model_json_schema() if s.input_model else {"type": "object", "properties": {}}
        out.append({
            "type": "function",
            "function": {"name": s.id, "description": s.description, "parameters": schema},
        })
    return out


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
