"""Audit logging for secrets operations.

Writes JSONL audit entries to the Buster logs directory. Entries are safe
for debugging and incident review and do NOT include secret material.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
import getpass
from buster.config.paths import get_paths


def _log_path():
    p = get_paths().logs_dir / "secrets_audit.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_event(event: str, vault: str, name: str | None = None, success: bool = True, note: str | None = None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": getpass.getuser(),
        "event": event,
        "vault": vault,
        "name": name,
        "success": success,
        "note": note,
    }
    p = _log_path()
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
