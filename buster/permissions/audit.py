"""Append-only audit log. Records tools, models, inference location, and whether
data left the machine or local network. Secrets are never logged."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from buster.database import get_database


def audit(
    *,
    category: str,
    detail: dict | None = None,
    task_id: str | None = None,
    workspace: str = "default",
    user: str = "",
    risk_level: int | None = None,
    approved: bool | None = None,
    result: str = "",
    model: str = "",
    inference_location: str = "",
    external_data_shared: bool = False,
) -> None:
    ts = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    get_database().execute(
        "INSERT INTO audit_log (timestamp, user, workspace, task_id, category, detail, risk_level, "
        "approved, result, model, inference_location, external_data_shared) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ts, user, workspace, task_id, category, json.dumps(_redact(detail or {})),
            risk_level, int(approved) if approved is not None else None, result, model,
            inference_location, int(external_data_shared),
        ),
    )


_SECRET_KEYS = ("password", "token", "secret", "api_key", "apikey", "authorization", "cookie")


def _redact(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if any(s in k.lower() for s in _SECRET_KEYS):
            out[k] = "***redacted***"
        elif isinstance(v, dict):
            out[k] = _redact(v)
        else:
            out[k] = v
    return out


def recent(limit: int = 100) -> list[dict]:
    rows = get_database().query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
        out.append(d)
    return out
