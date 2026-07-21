"""Build a bounded context bundle for a task.

We never load whole memory files into a request. We retrieve only the relevant
memory sections (FTS5) plus the personality preamble and a compact tool summary.
Categories loaded are reported via a context.loaded event.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from buster.memory import get_memory
from buster.personality import get_personality


class ContextBundle(BaseModel):
    system_preamble: str
    memory_snippets: list[str] = Field(default_factory=list)
    categories_loaded: list[str] = Field(default_factory=list)
    token_estimate: int = 0


def build_context(query: str, memory_limit: int = 5) -> ContextBundle:
    preamble = get_personality().system_preamble()
    categories = ["personality"]
    snippets: list[str] = []
    try:
        hits = get_memory().search(query, limit=memory_limit)
        for h in hits:
            label = h.heading_path or h.path
            snippets.append(f"[memory: {label}] {h.text}")
        if snippets:
            categories.append("memory")
    except Exception:  # noqa: BLE001
        pass

    text = preamble + "\n".join(snippets)
    return ContextBundle(
        system_preamble=preamble,
        memory_snippets=snippets,
        categories_loaded=categories,
        token_estimate=max(1, len(text) // 4),
    )
