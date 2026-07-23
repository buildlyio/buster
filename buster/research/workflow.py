"""Quick research workflow: search → fetch → save sources → generate report.

Deterministic scaffolding that works even with no LLM: it collects and organizes
sources into a structured Markdown report. When a model is available the agent
can enrich findings, but the pipeline never fabricates sources or "verifies"
them — it only records what was retrieved.
"""

from __future__ import annotations

from buster.events import Event, EventType, get_event_bus
from buster.reports import get_report_store
from buster.reports.model import Finding, Report, ReportSource
from buster.reports.store import slugify
from buster.research import get_research_manager
from buster.research.fetch import fetch_url
from buster.research.search import get_search_provider


async def run_quick_research(question: str, max_sources: int = 5) -> dict:
    bus = get_event_bus()
    rm = get_research_manager()
    project = rm.create_project(question)
    await bus.publish(Event(type=EventType.RESEARCH_STARTED, title=question,
                            metadata={"project_id": project.id}))

    provider = get_search_provider()
    results = await provider.search(question, limit=max_sources)

    report_sources: list[ReportSource] = []
    findings: list[Finding] = []
    for item in results:
        await bus.publish(Event(type=EventType.RESEARCH_SOURCE_FOUND, title=item.title,
                                metadata={"url": item.url}))
        try:
            page = await fetch_url(item.url)
        except Exception:  # noqa: BLE001
            continue
        src = rm.save_source(project.id, page, publisher="")
        await bus.publish(Event(type=EventType.RESEARCH_SOURCE_SAVED, title=src.title or src.url,
                                metadata={"source_id": src.id}))
        report_sources.append(ReportSource(
            id=src.id, url=src.url, title=src.title or item.title,
            published_at=src.published_at, retrieved_at=src.retrieved_at, trust=src.trust,
        ))
        # Snippet becomes a single-source claim (never "verified").
        if item.snippet:
            findings.append(Finding(statement=item.snippet, support="single_source",
                                    sources=[src.id]))

    # Synthesize proposed solutions + a one-click agent action (propose only).
    from buster.reports.model import Recommendation
    from buster.research.solutions import synthesize

    solution_set = await synthesize(question, findings)
    recommendations = [Recommendation(text=s.title, rationale=s.detail)
                       for s in solution_set.solutions]

    store = get_report_store()
    report = Report(
        id=store.new_id(),
        title=f"Research: {question}",
        slug=slugify(question),
        summary=f"Collected {len(report_sources)} source(s) for: {question}",
        findings=findings,
        recommendations=recommendations,
        sources=report_sources,
        notes="Sources were retrieved, not independently verified. Review before relying on claims.",
    )
    saved = store.save(report)
    rm.write_report_md(project.id, saved.to_markdown())
    await bus.publish(Event(type=EventType.RESEARCH_REPORT_UPDATED, title=report.title,
                            metadata={"report_id": saved.id, "project_id": project.id}))

    return {
        "project_id": project.id,
        "report_id": saved.id,
        "sources": len(report_sources),
        "title": report.title,
        "solutions": [s.model_dump() for s in solution_set.solutions],
        "action": solution_set.action.model_dump() if solution_set.action else None,
        "solutions_engine": solution_set.engine,
    }
