"""Structured report model + Markdown rendering.

Reports are structured objects, not just chat text. They distinguish supported
findings, single-source claims, conflicting evidence, inferences, unknowns, and
recommendations. Buster never claims a source is "verified" when it has only
been retrieved.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Finding(BaseModel):
    statement: str
    support: str = "single_source"   # supported | single_source | conflicting | inference | unknown
    sources: list[str] = Field(default_factory=list)  # source ids/urls


class Recommendation(BaseModel):
    text: str
    rationale: str = ""


class ReportSection(BaseModel):
    heading: str
    body: str = ""


class ReportSource(BaseModel):
    id: str = ""
    url: str
    title: str = ""
    publisher: str = ""
    published_at: str = ""
    retrieved_at: str = ""
    trust: str = "unrated"


class Report(BaseModel):
    id: str
    title: str
    slug: str
    kind: str = "research"
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    sources: list[ReportSource] = Field(default_factory=list)
    notes: str = ""
    sections: list[ReportSection] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    version: int = 1

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        if self.summary:
            lines += ["## Summary", "", self.summary, ""]
        if self.findings:
            lines += ["## Findings", ""]
            labels = {
                "supported": "Supported",
                "single_source": "Single-source claim",
                "conflicting": "Conflicting evidence",
                "inference": "Inference",
                "unknown": "Unknown",
            }
            for f in self.findings:
                tag = labels.get(f.support, f.support)
                src = f" _(sources: {', '.join(f.sources)})_" if f.sources else ""
                lines.append(f"- **[{tag}]** {f.statement}{src}")
            lines.append("")
        if self.conflicts:
            lines += ["## Conflicts", ""]
            lines += [f"- {c}" for c in self.conflicts] + [""]
        for sec in self.sections:
            lines += [f"## {sec.heading}", "", sec.body, ""]
        if self.recommendations:
            lines += ["## Recommendations", ""]
            for r in self.recommendations:
                extra = f" — {r.rationale}" if r.rationale else ""
                lines.append(f"- {r.text}{extra}")
            lines.append("")
        if self.sources:
            lines += ["## Sources", ""]
            for i, s in enumerate(self.sources, 1):
                meta = " · ".join(x for x in [s.publisher, s.published_at, f"trust: {s.trust}"] if x)
                title = s.title or s.url
                lines.append(f"{i}. [{title}]({s.url})" + (f" — {meta}" if meta else ""))
            lines.append("")
        if self.notes:
            lines += ["## Notes", "", self.notes, ""]
        lines += ["---", f"_Report {self.id} · version {self.version} · updated {self.updated_at}_"]
        return "\n".join(lines)
