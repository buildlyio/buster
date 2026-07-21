"""Buildly Workspace adapter interface + a mock adapter for Phase 1.

Phase 1 does not require production Buildly APIs. The mock adapter returns
representative Labs/CollabHub data so CLI and web can display items. Real MCP
(local or hosted) adapters plug in behind the same Protocol later.
"""

from __future__ import annotations

from typing import Protocol

from buster.buildly.models import (
    BuildlyEvent,
    BuildlyFeature,
    BuildlyIssue,
    BuildlyNotification,
    BuildlyOpportunity,
    BuildlyProduct,
    BuildlyRelease,
)
from buster.config import load_config


class BuildlyAdapter(Protocol):
    async def products(self) -> list[BuildlyProduct]: ...
    async def features(self, product_id: str) -> list[BuildlyFeature]: ...
    async def issues(self, product_id: str) -> list[BuildlyIssue]: ...
    async def opportunities(self) -> list[BuildlyOpportunity]: ...
    async def events(self) -> list[BuildlyEvent]: ...
    async def releases(self, product_id: str) -> list[BuildlyRelease]: ...
    async def notifications(self) -> list[BuildlyNotification]: ...


class MockBuildlyAdapter:
    """Deterministic mock data (Labs + CollabHub) for onboarding/demos/tests."""

    async def products(self) -> list[BuildlyProduct]:
        return [
            BuildlyProduct(id="prod_buster", name="Buster", description="Local-first assistant"),
        ]

    async def features(self, product_id: str) -> list[BuildlyFeature]:
        return [
            BuildlyFeature(
                id="feat_lcdp", product_id=product_id,
                name="Local Capability Discovery", status="in_progress",
                description="Discover local capabilities and Buster nodes.",
            ),
        ]

    async def issues(self, product_id: str) -> list[BuildlyIssue]:
        return [
            BuildlyIssue(id="iss_1", product_id=product_id, title="Onboarding polish",
                         status="open", feature_id="feat_lcdp"),
        ]

    async def opportunities(self) -> list[BuildlyOpportunity]:
        return [
            BuildlyOpportunity(id="opp_1", title="Edge AI pilot",
                               summary="Deploy local assistants on small Linux boxes.",
                               tags=["edge", "local-first"]),
        ]

    async def events(self) -> list[BuildlyEvent]:
        return [BuildlyEvent(id="evt_1", title="Buildly community call", url="https://buildly.io")]

    async def releases(self, product_id: str) -> list[BuildlyRelease]:
        return [BuildlyRelease(id="rel_1", product_id=product_id, version="0.1.0",
                               notes="Buster Phase 1 foundation.")]

    async def notifications(self) -> list[BuildlyNotification]:
        return [BuildlyNotification(id="ntf_1", kind="release", title="Buster 0.1.0",
                                    body="Phase 1 foundation available.")]


def get_buildly_adapter() -> BuildlyAdapter:
    """Return the active adapter. Phase 1 uses the mock; real modes come later."""
    config = load_config()
    # Future: mode == "local_mcp" / "hosted_mcp" → real MCP-backed adapter.
    _ = config.buildly.mode
    return MockBuildlyAdapter()
