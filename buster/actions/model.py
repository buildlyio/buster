"""Structured action-plan records.

Commands are represented as fixed argv lists constructed by trusted catalog code
— never assembled from arbitrary model text. The model may *select* a catalog
action, but cannot inject shell strings.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ActionStep(BaseModel):
    # argv list, executed without a shell. No string interpolation from models.
    command: list[str]
    description: str = ""


class Verification(BaseModel):
    # HTTP GET that should succeed, or a command whose exit code should be 0.
    request: str = ""
    command: list[str] = Field(default_factory=list)
    expect_status: int = 200


class ActionPlan(BaseModel):
    id: str = ""
    title: str
    risk_level: int
    preconditions: list[str] = Field(default_factory=list)
    steps: list[ActionStep] = Field(default_factory=list)
    verification: list[Verification] = Field(default_factory=list)
    rollback: list[ActionStep] = Field(default_factory=list)

    def preview(self) -> str:
        lines = [f"{self.title}  (risk level {self.risk_level})", ""]
        if self.preconditions:
            lines.append("Preconditions:")
            lines += [f"  - {p}" for p in self.preconditions]
        lines.append("Actions:")
        for s in self.steps:
            lines.append(f"  $ {' '.join(s.command)}")
        if self.verification:
            lines.append("Verification:")
            for v in self.verification:
                if v.request:
                    lines.append(f"  GET {v.request} (expect {v.expect_status})")
                elif v.command:
                    lines.append(f"  $ {' '.join(v.command)} (expect exit 0)")
        if self.rollback:
            lines.append("Rollback:")
            for s in self.rollback:
                lines.append(f"  $ {' '.join(s.command)}")
        return "\n".join(lines)
