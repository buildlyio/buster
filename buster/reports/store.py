"""Report persistence: Markdown on disk + SQLite index. Stored once, everywhere."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from buster.config import get_paths
from buster.database import get_database
from buster.reports.model import Report


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "report"


class ReportStore:
    def __init__(self) -> None:
        self.dir = get_paths().reports_dir

    def save(self, report: Report, workspace: str = "default") -> Report:
        db = get_database()
        now = _now()
        if not report.created_at:
            report.created_at = now
        report.updated_at = now
        existing = db.query_one("SELECT version, path FROM reports WHERE id = ?", (report.id,))
        if existing:
            report.version = existing["version"] + 1
            path = Path(existing["path"])
        else:
            path = self.dir / f"{report.slug}-{report.id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.to_markdown(), encoding="utf-8")
        db.execute(
            "INSERT INTO reports (id, workspace, title, slug, kind, path, summary, created_at, "
            "updated_at, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, summary=excluded.summary, "
            "updated_at=excluded.updated_at, version=excluded.version, path=excluded.path",
            (report.id, workspace, report.title, report.slug, report.kind, str(path),
             report.summary, report.created_at, report.updated_at, report.version),
        )
        return report

    def new_id(self) -> str:
        return f"report_{uuid.uuid4().hex[:12]}"

    def list(self, limit: int = 50) -> list[dict]:
        rows = get_database().query("SELECT * FROM reports ORDER BY updated_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def get_markdown(self, report_id: str) -> str | None:
        row = get_database().query_one("SELECT path FROM reports WHERE id = ?", (report_id,))
        if not row:
            return None
        path = Path(row["path"])
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_meta(self, report_id: str) -> dict | None:
        row = get_database().query_one("SELECT * FROM reports WHERE id = ?", (report_id,))
        return dict(row) if row else None


@lru_cache(maxsize=1)
def get_report_store() -> ReportStore:
    return ReportStore()
