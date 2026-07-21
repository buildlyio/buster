"""Prompt library.

Stores separately: the original user prompt, automatically-added context, and
the final executed prompt, plus the outcome. Default visibility is private;
community sharing is deferred but the field exists.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from functools import lru_cache

from pydantic import BaseModel, Field

from buster.database import get_database
from buster.permissions.audit import _redact


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class PromptRecord(BaseModel):
    id: str
    workspace: str = "default"
    title: str
    product: str = ""
    linked_items: dict = Field(default_factory=lambda: {"features": [], "issues": []})
    source: dict = Field(default_factory=dict)
    original_prompt: str = ""
    resolved_context: str = ""
    final_prompt: str = ""
    outcome: dict = Field(default_factory=lambda: {"status": "draft"})
    tags: list[str] = Field(default_factory=list)
    visibility: str = "private"
    is_template: bool = False
    created_at: str = ""

    def to_markdown(self) -> str:
        return (
            f"# {self.title}\n\n"
            f"- id: {self.id}\n- workspace: {self.workspace}\n- product: {self.product}\n"
            f"- visibility: {self.visibility}\n- tags: {', '.join(self.tags)}\n\n"
            f"## Original prompt\n\n{self.original_prompt}\n\n"
            f"## Resolved context\n\n{self.resolved_context}\n\n"
            f"## Final prompt\n\n{self.final_prompt}\n\n"
            f"## Outcome\n\n```json\n{json.dumps(self.outcome, indent=2)}\n```\n"
        )


class PromptService:
    def save(self, record: PromptRecord) -> PromptRecord:
        if not record.id:
            record.id = f"prompt_{uuid.uuid4().hex[:10]}"
        if not record.created_at:
            record.created_at = _now()
        # Redact secrets from stored prompt text metadata.
        record.source = _redact(record.source)
        get_database().execute(
            "INSERT INTO prompt_records (id, workspace, title, product, linked_items, source, "
            "original_prompt, resolved_context, final_prompt, outcome, tags, visibility, is_template, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, outcome=excluded.outcome, "
            "tags=excluded.tags, visibility=excluded.visibility, is_template=excluded.is_template",
            (
                record.id, record.workspace, record.title, record.product,
                json.dumps(record.linked_items), json.dumps(record.source),
                record.original_prompt, record.resolved_context, record.final_prompt,
                json.dumps(record.outcome), json.dumps(record.tags), record.visibility,
                int(record.is_template), record.created_at,
            ),
        )
        return record

    def get(self, prompt_id: str) -> PromptRecord | None:
        row = get_database().query_one("SELECT * FROM prompt_records WHERE id = ?", (prompt_id,))
        return self._row(row) if row else None

    def list(self, limit: int = 50) -> list[PromptRecord]:
        rows = get_database().query(
            "SELECT * FROM prompt_records ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._row(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> list[PromptRecord]:
        db = get_database()
        try:
            rows = db.query(
                "SELECT p.* FROM prompts_fts JOIN prompt_records p ON p.rowid = prompts_fts.rowid "
                "WHERE prompts_fts MATCH ? ORDER BY bm25(prompts_fts) LIMIT ?",
                (_fts(query), limit),
            )
        except Exception:
            rows = db.query(
                "SELECT * FROM prompt_records WHERE title LIKE ? OR original_prompt LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            )
        return [self._row(r) for r in rows]

    def link(self, prompt_id: str, kind: str, item_id: str) -> None:
        rec = self.get(prompt_id)
        if not rec:
            raise KeyError(prompt_id)
        rec.linked_items.setdefault(kind, [])
        if item_id not in rec.linked_items[kind]:
            rec.linked_items[kind].append(item_id)
        get_database().execute(
            "UPDATE prompt_records SET linked_items = ? WHERE id = ?",
            (json.dumps(rec.linked_items), prompt_id),
        )

    def _row(self, r) -> PromptRecord:
        return PromptRecord(
            id=r["id"], workspace=r["workspace"], title=r["title"], product=r["product"],
            linked_items=json.loads(r["linked_items"]), source=json.loads(r["source"]),
            original_prompt=r["original_prompt"], resolved_context=r["resolved_context"],
            final_prompt=r["final_prompt"], outcome=json.loads(r["outcome"]),
            tags=json.loads(r["tags"]), visibility=r["visibility"],
            is_template=bool(r["is_template"]), created_at=r["created_at"],
        )


def _fts(q: str) -> str:
    terms = [t for t in q.replace('"', " ").split() if t]
    return " OR ".join(f'"{t}"' for t in terms) or '""'


@lru_cache(maxsize=1)
def get_prompts() -> PromptService:
    return PromptService()
