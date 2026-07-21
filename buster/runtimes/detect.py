"""Detect available agent runtimes and persist their records."""

from __future__ import annotations

from datetime import UTC, datetime

from buster.config import load_config
from buster.database import get_database
from buster.runtimes.adapters import BusterSelfAdapter, HermesAdapter, OpenClawAdapter
from buster.runtimes.base import RuntimeInfo


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


async def detect_runtimes() -> list[RuntimeInfo]:
    config = load_config()
    infos: list[RuntimeInfo] = []
    infos.append(await BusterSelfAdapter().detect())
    if config.runtimes.detect:
        for adapter in (HermesAdapter(), OpenClawAdapter()):
            info = await adapter.detect()
            if info:
                infos.append(info)

    db = get_database()
    now = _now()
    for info in infos:
        existing = db.query_one("SELECT trust FROM runtimes WHERE id = ?", (info.id,))
        trust = existing["trust"] if existing else info.trust
        db.execute(
            "INSERT INTO runtimes (id, runtime_type, name, detected_via, status, manifest, trust, "
            "discovered_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, manifest=excluded.manifest, "
            "last_seen_at=excluded.last_seen_at",
            (info.id, info.runtime_type, info.name, info.detected_via, info.status.value,
             info.model_dump_json(), trust, now, now),
        )
    return infos
