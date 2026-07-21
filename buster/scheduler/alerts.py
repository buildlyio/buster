"""Alert storage. Alerts are deterministic; the LLM may explain but not detect."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import lru_cache

from pydantic import BaseModel

from buster.database import get_database


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class Alert(BaseModel):
    id: str
    code: str
    severity: str
    title: str
    detail: str = ""
    created_at: str
    acknowledged: bool = False


class AlertStore:
    def raise_alert(self, code: str, title: str, severity: str = "warning", detail: str = "") -> Alert | None:
        """Create an alert if an unacknowledged one with the same code isn't open."""
        db = get_database()
        existing = db.query_one(
            "SELECT id FROM alerts WHERE code = ? AND acknowledged = 0 AND resolved_at IS NULL",
            (code,),
        )
        if existing:
            return None
        aid = f"alert_{uuid.uuid4().hex[:10]}"
        now = _now()
        db.execute(
            "INSERT INTO alerts (id, code, severity, title, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (aid, code, severity, title, detail, now),
        )
        return Alert(id=aid, code=code, severity=severity, title=title, detail=detail, created_at=now)

    def resolve(self, code: str) -> None:
        get_database().execute(
            "UPDATE alerts SET resolved_at = ? WHERE code = ? AND resolved_at IS NULL",
            (_now(), code),
        )

    def acknowledge(self, alert_id: str) -> None:
        get_database().execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))

    def list(self, include_resolved: bool = False, limit: int = 100) -> list[dict]:
        db = get_database()
        if include_resolved:
            rows = db.query("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,))
        else:
            rows = db.query(
                "SELECT * FROM alerts WHERE resolved_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def get_alerts() -> AlertStore:
    return AlertStore()
