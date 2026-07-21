"""Structured diagnostic result models (shared by system/network/doctor)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class CheckResult(BaseModel):
    check: str
    status: CheckStatus
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


def worst(results: list[CheckResult]) -> CheckStatus:
    order = [CheckStatus.OK, CheckStatus.UNKNOWN, CheckStatus.WARNING, CheckStatus.CRITICAL]
    rank = {s: i for i, s in enumerate(order)}
    return max((r.status for r in results), key=lambda s: rank[s], default=CheckStatus.OK)
