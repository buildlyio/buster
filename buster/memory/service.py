"""Markdown memory service.

Durable, human-readable context lives as Markdown under data/memory/. Files are
split by heading into sections and indexed into SQLite FTS5 for retrieval. We
never load whole files into a model request — the context builder pulls only the
relevant sections.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from buster.config import get_paths
from buster.database import get_database

# Standard memory subdirectories (created on demand).
_SUBDIRS = ["personality", "personal", "projects", "system", "procedures", "incidents"]


class MemoryHit(BaseModel):
    id: str
    path: str
    heading_path: str
    text: str
    importance: int
    score: float = 0.0


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_sections(md: str) -> list[tuple[str, str]]:
    """Split Markdown into (heading_path, body) by heading. A preamble before
    the first heading is captured under an empty heading path."""
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    current_heading = ""
    buf: list[str] = []

    def flush(heading: str) -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((heading, body))

    for line in md.splitlines():
        if line.startswith("#"):
            flush(current_heading)
            buf = []
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_heading = " > ".join(t for _, t in stack)
        else:
            buf.append(line)
    flush(current_heading)
    return sections


class MemoryService:
    def __init__(self) -> None:
        self.root = get_paths().memory_dir
        for sub in _SUBDIRS:
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # -- writing --------------------------------------------------------------

    def write_note(self, category: str, name: str, content: str) -> Path:
        """Write a Markdown note and index it. category is a subdirectory."""
        safe = category if category in _SUBDIRS else "personal"
        path = self.root / safe / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.index_file(path)
        return path

    def index_file(self, path: Path) -> int:
        """(Re)index a single Markdown file. Returns sections indexed."""
        db = get_database()
        rel = str(path)
        db.execute("DELETE FROM memories WHERE path = ?", (rel,))
        md = path.read_text(encoding="utf-8")
        mtime = _now()
        count = 0
        for heading, body in _split_sections(md):
            db.execute(
                "INSERT INTO memories (id, workspace, path, heading_path, text, content_hash, "
                "modified_at, importance, retention, token_estimate) "
                "VALUES (?, 'default', ?, ?, ?, ?, ?, 3, 'durable', ?)",
                (
                    uuid.uuid4().hex,
                    rel,
                    heading,
                    body,
                    hashlib.sha256(body.encode()).hexdigest(),
                    mtime,
                    _estimate_tokens(body),
                ),
            )
            count += 1
        return count

    def reindex_all(self) -> int:
        db = get_database()
        db.execute("DELETE FROM memories", ())
        total = 0
        for path in self.root.rglob("*.md"):
            total += self.index_file(path)
        return total

    # -- retrieval ------------------------------------------------------------

    def search(self, query: str, limit: int = 8) -> list[MemoryHit]:
        db = get_database()
        # bm25() ranks; lower is better, so negate for a friendly score.
        try:
            rows = db.query(
                "SELECT m.id, m.path, m.heading_path, m.text, m.importance, "
                "bm25(memories_fts) AS rank "
                "FROM memories_fts JOIN memories m ON m.rowid = memories_fts.rowid "
                "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (_fts_query(query), limit),
            )
        except Exception:
            # Fallback to LIKE if FTS query syntax rejects the input.
            rows = db.query(
                "SELECT id, path, heading_path, text, importance, 0 AS rank "
                "FROM memories WHERE text LIKE ? LIMIT ?",
                (f"%{query}%", limit),
            )
        return [
            MemoryHit(
                id=r["id"],
                path=r["path"],
                heading_path=r["heading_path"],
                text=r["text"],
                importance=r["importance"],
                score=-float(r["rank"]) if r["rank"] else 0.0,
            )
            for r in rows
        ]


def _fts_query(q: str) -> str:
    # Quote terms to avoid FTS5 syntax errors on punctuation.
    terms = [t for t in q.replace('"', " ").split() if t]
    return " OR ".join(f'"{t}"' for t in terms) or '""'


@lru_cache(maxsize=1)
def get_memory() -> MemoryService:
    return MemoryService()
