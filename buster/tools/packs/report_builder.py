"""Report builder tool pack: create structured Markdown reports."""

from __future__ import annotations

from pydantic import BaseModel

from buster.reports import get_report_store
from buster.reports.model import Finding, Recommendation, Report, ReportSource
from buster.reports.store import slugify
from buster.tools.registry import tool


class CreateReportArgs(BaseModel):
    title: str
    summary: str = ""
    findings: list[dict] = []
    recommendations: list[dict] = []
    sources: list[dict] = []
    notes: str = ""


class CreateReportResult(BaseModel):
    report_id: str
    path: str


@tool(
    id="report.create",
    description="Create a structured Markdown report from findings and sources.",
    pack="report_builder",
    permission="write",
    risk_level=1,
)
async def create_report(args: CreateReportArgs) -> CreateReportResult:
    store = get_report_store()
    report = Report(
        id=store.new_id(),
        title=args.title,
        slug=slugify(args.title),
        summary=args.summary,
        findings=[Finding.model_validate(f) for f in args.findings],
        recommendations=[Recommendation.model_validate(r) for r in args.recommendations],
        sources=[ReportSource.model_validate(s) for s in args.sources],
        notes=args.notes,
    )
    saved = store.save(report)
    meta = store.get_meta(saved.id)
    return CreateReportResult(report_id=saved.id, path=meta["path"] if meta else "")
