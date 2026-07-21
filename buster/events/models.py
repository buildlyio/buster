"""Typed event model.

Events describe *what Buster is doing* — never raw model chain-of-thought.
The same objects are persisted to ``task_events``, streamed over SSE to the web
client, and rendered in the terminal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    ASSISTANT_STATUS = "assistant.status"
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    PLAN_CREATED = "plan.created"
    MODEL_SELECTED = "model.selected"
    CONTEXT_LOADED = "context.loaded"
    RESEARCH_STARTED = "research.started"
    RESEARCH_SOURCE_FOUND = "research.source_found"
    RESEARCH_SOURCE_SAVED = "research.source_saved"
    RESEARCH_REPORT_UPDATED = "research.report_updated"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    PERMISSION_REQUESTED = "permission.requested"
    PERMISSION_APPROVED = "permission.approved"
    PERMISSION_DENIED = "permission.denied"
    ACTION_STARTED = "action.started"
    ACTION_VERIFIED = "action.verified"
    ALERT_CREATED = "alert.created"
    SERVICE_DISCOVERED = "service.discovered"
    NODE_DISCOVERED = "node.discovered"
    RUNTIME_DISCOVERED = "runtime.discovered"
    # streaming chat token deltas (content only, never reasoning)
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETED = "message.completed"


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class Event(BaseModel):
    type: EventType
    timestamp: str = Field(default_factory=_now)
    task_id: str | None = None
    title: str = ""
    tool: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def sse(self) -> str:
        """Serialize as a Server-Sent Event frame."""
        return f"event: {self.type.value}\ndata: {self.model_dump_json()}\n\n"
