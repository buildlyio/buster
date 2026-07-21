"""Core tool pack: identity, time, capability profile."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from buster.models.capability import detect_capabilities
from buster.tools.registry import tool


class Empty(BaseModel):
    pass


class NowResult(BaseModel):
    iso: str
    timezone: str


@tool(id="core.now", description="Return the current local date and time.", pack="core")
async def now(_: Empty | None = None) -> NowResult:
    dt = datetime.now(UTC).astimezone()
    return NowResult(iso=dt.isoformat(timespec="seconds"), timezone=str(dt.tzinfo))


class CapabilityResult(BaseModel):
    profile: dict


@tool(
    id="core.capabilities",
    description="Report this machine's detected hardware capability profile.",
    pack="core",
)
async def capabilities(_: Empty | None = None) -> CapabilityResult:
    return CapabilityResult(profile=detect_capabilities().model_dump())
