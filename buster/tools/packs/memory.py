"""Memory tool pack: search and write durable Markdown memory."""

from __future__ import annotations

from pydantic import BaseModel

from buster.memory import get_memory
from buster.tools.registry import tool


class SearchArgs(BaseModel):
    query: str
    limit: int = 8


class SearchResult(BaseModel):
    hits: list[dict]


@tool(
    id="memory.search",
    description="Search indexed Markdown memory via SQLite FTS5.",
    pack="memory",
    permission="read",
)
async def memory_search(args: SearchArgs) -> SearchResult:
    hits = get_memory().search(args.query, limit=args.limit)
    return SearchResult(hits=[h.model_dump() for h in hits])


class WriteArgs(BaseModel):
    category: str = "personal"
    name: str
    content: str


class WriteResult(BaseModel):
    path: str


@tool(
    id="memory.write",
    description="Write a durable Markdown memory note and index it.",
    pack="memory",
    permission="write",
    risk_level=1,
)
async def memory_write(args: WriteArgs) -> WriteResult:
    path = get_memory().write_note(args.category, args.name, args.content)
    return WriteResult(path=str(path))
