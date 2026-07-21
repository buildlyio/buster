"""Permission service: risk levels + request/approve/deny flow.

Risk levels (spec):
  0 read-only            — normally allowed
  1 safe Buster-owned    — may be pre-approved (restart Buster, clear cache, ...)
  2 system-changing      — always request confirmation (restart Ollama, ...)
  3 destructive          — exact preview + explicit confirmation (delete, reboot)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import IntEnum
from functools import lru_cache

from pydantic import BaseModel

from buster.database import get_database
from buster.events import Event, EventType, get_event_bus


class RiskLevel(IntEnum):
    READ_ONLY = 0
    SAFE_BUSTER = 1
    SYSTEM_CHANGING = 2
    DESTRUCTIVE = 3


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class PermissionRequest(BaseModel):
    id: str
    task_id: str | None = None
    action_id: str | None = None
    risk_level: int
    summary: str
    status: str = "requested"
    created_at: str
    decided_at: str | None = None
    decided_by: str = ""


class PermissionService:
    def auto_approvable(self, risk_level: int) -> bool:
        """Level 0 always; level 1 may be pre-approved (config could gate this)."""
        return risk_level <= RiskLevel.SAFE_BUSTER

    async def request(
        self, risk_level: int, summary: str, task_id: str | None = None, action_id: str | None = None
    ) -> PermissionRequest:
        db = get_database()
        pid = f"perm_{uuid.uuid4().hex[:10]}"
        now = _now()
        db.execute(
            "INSERT INTO permissions (id, task_id, action_id, risk_level, summary, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'requested', ?)",
            (pid, task_id, action_id, risk_level, summary, now),
        )
        req = PermissionRequest(id=pid, task_id=task_id, action_id=action_id,
                                risk_level=risk_level, summary=summary, created_at=now)
        await get_event_bus().publish(
            Event(type=EventType.PERMISSION_REQUESTED, task_id=task_id, title=summary,
                  metadata={"permission_id": pid, "risk_level": risk_level})
        )
        return req

    async def decide(self, permission_id: str, approved: bool, decided_by: str = "user") -> None:
        db = get_database()
        status = "approved" if approved else "denied"
        db.execute(
            "UPDATE permissions SET status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
            (status, _now(), decided_by, permission_id),
        )
        row = db.query_one("SELECT task_id, summary FROM permissions WHERE id = ?", (permission_id,))
        evt = EventType.PERMISSION_APPROVED if approved else EventType.PERMISSION_DENIED
        await get_event_bus().publish(
            Event(type=evt, task_id=row["task_id"] if row else None,
                  title=row["summary"] if row else "", metadata={"permission_id": permission_id})
        )

    def get(self, permission_id: str) -> PermissionRequest | None:
        row = get_database().query_one("SELECT * FROM permissions WHERE id = ?", (permission_id,))
        return PermissionRequest.model_validate(dict(row)) if row else None

    def pending(self) -> list[PermissionRequest]:
        rows = get_database().query(
            "SELECT * FROM permissions WHERE status = 'requested' ORDER BY created_at"
        )
        return [PermissionRequest.model_validate(dict(r)) for r in rows]


@lru_cache(maxsize=1)
def get_permissions() -> PermissionService:
    return PermissionService()
