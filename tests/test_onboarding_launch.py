"""Onboarding/launch UX: model verification, guide, success reporting."""

import pytest

from buster.config import BusterConfig
from buster.models import verify


@pytest.mark.asyncio
async def test_verify_model_ok(monkeypatch):
    from buster.models.provider import ChatResponse
    from buster.models.router import RouteDecision

    class FakeProvider:
        name = "ollama"

        async def chat(self, req):
            return ChatResponse(model=req.model, provider="ollama",
                                inference_location="lan", content="OK")

    async def fake_route(self, **kw):
        return RouteDecision(provider=FakeProvider(), model="gemma3:latest",
                             location="lan", external_data_shared=False, reason="ok")

    monkeypatch.setattr("buster.models.router.ModelRouter.route", fake_route)
    check = await verify.verify_model(BusterConfig())
    assert check.ok is True
    assert check.model == "gemma3:latest" and check.location == "lan"


@pytest.mark.asyncio
async def test_verify_model_no_model(monkeypatch):
    from buster.models.router import RouteDecision

    async def fake_route(self, **kw):
        from buster.models.disabled import DisabledProvider

        return RouteDecision(provider=DisabledProvider(), model="none",
                             location="unknown", external_data_shared=False,
                             reason="No model available.")

    monkeypatch.setattr("buster.models.router.ModelRouter.route", fake_route)
    check = await verify.verify_model(BusterConfig())
    assert check.ok is False
    assert "no model" in check.detail.lower()


@pytest.mark.asyncio
async def test_verify_model_reports_provider_error(monkeypatch):
    from buster.models.router import RouteDecision

    class BrokenProvider:
        name = "ollama"

        async def chat(self, req):
            raise ConnectionError("connection refused")

    async def fake_route(self, **kw):
        return RouteDecision(provider=BrokenProvider(), model="gemma3:latest",
                             location="lan", external_data_shared=False, reason="ok")

    monkeypatch.setattr("buster.models.router.ModelRouter.route", fake_route)
    check = await verify.verify_model(BusterConfig())
    assert check.ok is False
    assert "unreachable" in check.detail.lower()


def test_friendly_error_classification():
    assert "unreachable" in verify._friendly_error("Connection refused").lower()
    assert "not found" in verify._friendly_error("HTTP 404 model not found").lower()
    assert "auth" in verify._friendly_error("HTTP 401 unauthorized").lower()


def test_guide_renders(capsys):
    from rich.console import Console

    from buster.cli.guide import print_guide

    print_guide(Console())
    # Smoke test: it printed the guide without raising.
