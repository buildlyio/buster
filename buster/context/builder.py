"""Build a bounded context bundle for a task.

We never load whole memory files into a request. We retrieve only the relevant
memory sections (FTS5) plus the personality preamble and a compact tool summary.
Categories loaded are reported via a context.loaded event.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from buster.memory import get_memory
from buster.personality import get_personality
from buster.tools import get_registry


class ContextBundle(BaseModel):
    system_preamble: str
    memory_snippets: list[str] = Field(default_factory=list)
    categories_loaded: list[str] = Field(default_factory=list)
    token_estimate: int = 0


def _capability_context() -> str:
    """What Buster actually is and can do — so it answers as Buster, not as a
    generic assistant. Built from the live tool registry."""
    try:
        summary = get_registry().capability_summary()
    except Exception:  # noqa: BLE001
        summary = ""
    return (
        "About you: you are Buster, a local-first assistant that runs on the "
        "user's own machine. Your focus is practical work, not open-ended chat. "
        "When asked what you can do, describe THESE concrete capabilities (do not "
        "give a generic chatbot answer):\n"
        f"{summary}\n"
        "You prefer local models, keep data on the machine, and always ask before "
        "taking system-changing actions. If a request maps to one of your "
        "capabilities, say how you'd do it with your tools rather than answering "
        "abstractly."
    )


def build_context(query: str, memory_limit: int = 5) -> ContextBundle:
    preamble = get_personality().system_preamble()
    capability = _capability_context()
    categories = ["personality", "capabilities"]
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

    # Capability context is part of the system preamble so the model always sees it.
    full_preamble = f"{preamble}\n\n{capability}"
    text = full_preamble + "\n".join(snippets)
    return ContextBundle(
        system_preamble=full_preamble,
        memory_snippets=snippets,
        categories_loaded=categories,
        token_estimate=max(1, len(text) // 4),
    )
