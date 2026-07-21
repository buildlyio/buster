"""Task and conversation persistence, shared across CLI and web clients."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from functools import lru_cache

from pydantic import BaseModel, Field

from buster.database import get_database


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Task(BaseModel):
    id: str
    workspace: str = "default"
    kind: str
    title: str
    status: str = "created"
    created_at: str
    updated_at: str
    metadata: dict = Field(default_factory=dict)


class Message(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    metadata: dict = Field(default_factory=dict)


class TaskStore:
    def create_task(self, kind: str, title: str, workspace: str = "default") -> Task:
        db = get_database()
        now = _now()
        tid = _id("task")
        db.execute(
            "INSERT INTO tasks (id, workspace, kind, title, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'created', ?, ?)",
            (tid, workspace, kind, title, now, now),
        )
        return Task(id=tid, workspace=workspace, kind=kind, title=title, created_at=now, updated_at=now)

    def set_status(self, task_id: str, status: str) -> None:
        get_database().execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), task_id)
        )

    def get(self, task_id: str) -> Task | None:
        row = get_database().query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._row_to_task(row) if row else None

    def list(self, limit: int = 50) -> list[Task]:
        rows = get_database().query("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        return [self._row_to_task(r) for r in rows]

    def _row_to_task(self, r) -> Task:
        return Task(
            id=r["id"], workspace=r["workspace"], kind=r["kind"], title=r["title"],
            status=r["status"], created_at=r["created_at"], updated_at=r["updated_at"],
            metadata=json.loads(r["metadata"]),
        )

    # -- conversations --------------------------------------------------------

    def create_conversation(self, title: str = "Conversation", workspace: str = "default") -> str:
        db = get_database()
        now = _now()
        cid = _id("conv")
        db.execute(
            "INSERT INTO conversations (id, workspace, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cid, workspace, title, now, now),
        )
        return cid

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict | None = None) -> Message:
        db = get_database()
        now = _now()
        mid = _id("msg")
        db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mid, conversation_id, role, content, now, json.dumps(metadata or {})),
        )
        db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return Message(id=mid, conversation_id=conversation_id, role=role, content=content,
                       created_at=now, metadata=metadata or {})

    def messages(self, conversation_id: str) -> list[Message]:
        rows = get_database().query(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at", (conversation_id,)
        )
        return [
            Message(id=r["id"], conversation_id=r["conversation_id"], role=r["role"],
                    content=r["content"], created_at=r["created_at"], metadata=json.loads(r["metadata"]))
            for r in rows
        ]

    def list_conversations(self, limit: int = 50) -> list[dict]:
        rows = get_database().query(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def get_task_store() -> TaskStore:
    return TaskStore()
