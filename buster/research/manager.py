"""Research manager: workspaces on disk + source records in SQLite.

Layout:
  data/research/<slug>-<date>/
    request.md  plan.md  sources.json  notes.md  report.md  action-plan.md  attachments/
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from buster.config import get_paths
from buster.database import get_database
from buster.reports.store import slugify
from buster.research.fetch import FetchedPage


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


class ResearchProject(BaseModel):
    id: str
    question: str
    slug: str
    dir: str
    status: str = "active"
    created_at: str
    updated_at: str


class Source(BaseModel):
    id: str
    project_id: str
    url: str
    title: str = ""
    publisher: str = ""
    author: str = ""
    published_at: str = ""
    retrieved_at: str = ""
    content_hash: str = ""
    text_path: str = ""
    trust: str = "unrated"
    notes: str = ""


class ResearchManager:
    def __init__(self) -> None:
        self.root = get_paths().research_dir

    def create_project(self, question: str) -> ResearchProject:
        db = get_database()
        slug = slugify(question)
        pid = f"research_{uuid.uuid4().hex[:12]}"
        dir_name = f"{slug}-{_today()}"
        proj_dir = self.root / dir_name
        (proj_dir / "attachments").mkdir(parents=True, exist_ok=True)
        (proj_dir / "request.md").write_text(f"# Research request\n\n{question}\n", encoding="utf-8")
        (proj_dir / "sources.json").write_text("[]", encoding="utf-8")
        (proj_dir / "notes.md").write_text(f"# Notes: {question}\n\n", encoding="utf-8")
        now = _now()
        db.execute(
            "INSERT INTO research_projects (id, workspace, question, slug, dir, status, created_at, updated_at) "
            "VALUES (?, 'default', ?, ?, ?, 'active', ?, ?)",
            (pid, question, slug, str(proj_dir), now, now),
        )
        return ResearchProject(id=pid, question=question, slug=slug, dir=str(proj_dir),
                               created_at=now, updated_at=now)

    def get_project(self, project_id: str) -> ResearchProject | None:
        row = get_database().query_one("SELECT * FROM research_projects WHERE id = ?", (project_id,))
        if not row:
            return None
        return ResearchProject(id=row["id"], question=row["question"], slug=row["slug"],
                               dir=row["dir"], status=row["status"], created_at=row["created_at"],
                               updated_at=row["updated_at"])

    def list_projects(self, limit: int = 50) -> list[ResearchProject]:
        rows = get_database().query(
            "SELECT * FROM research_projects ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [
            ResearchProject(id=r["id"], question=r["question"], slug=r["slug"], dir=r["dir"],
                            status=r["status"], created_at=r["created_at"], updated_at=r["updated_at"])
            for r in rows
        ]

    def save_source(self, project_id: str, page: FetchedPage, publisher: str = "") -> Source:
        proj = self.get_project(project_id)
        if not proj:
            raise KeyError(project_id)
        sid = f"src_{uuid.uuid4().hex[:10]}"
        # Persist extracted text to the project attachments dir.
        text_path = Path(proj.dir) / "attachments" / f"{sid}.txt"
        text_path.write_text(page.text, encoding="utf-8")
        src = Source(
            id=sid, project_id=project_id, url=page.url, title=page.title,
            publisher=publisher, published_at=page.published_at, retrieved_at=_now(),
            content_hash=page.content_hash, text_path=str(text_path),
        )
        get_database().execute(
            "INSERT INTO sources (id, project_id, url, title, publisher, author, published_at, "
            "retrieved_at, content_hash, text_path, trust, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (src.id, src.project_id, src.url, src.title, src.publisher, src.author,
             src.published_at, src.retrieved_at, src.content_hash, src.text_path, src.trust, src.notes),
        )
        self._rewrite_sources_json(proj)
        return src

    def sources(self, project_id: str) -> list[Source]:
        rows = get_database().query("SELECT * FROM sources WHERE project_id = ?", (project_id,))
        return [Source.model_validate(dict(r)) for r in rows]

    def add_note(self, project_id: str, text: str) -> None:
        proj = self.get_project(project_id)
        if not proj:
            raise KeyError(project_id)
        notes = Path(proj.dir) / "notes.md"
        with notes.open("a", encoding="utf-8") as fh:
            fh.write(f"\n- {text}\n")

    def _rewrite_sources_json(self, proj: ResearchProject) -> None:
        data = [s.model_dump() for s in self.sources(proj.id)]
        (Path(proj.dir) / "sources.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def write_report_md(self, project_id: str, markdown: str) -> Path:
        proj = self.get_project(project_id)
        if not proj:
            raise KeyError(project_id)
        path = Path(proj.dir) / "report.md"
        path.write_text(markdown, encoding="utf-8")
        return path


@lru_cache(maxsize=1)
def get_research_manager() -> ResearchManager:
    return ResearchManager()
