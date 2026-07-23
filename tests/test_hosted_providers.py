"""P2.4 — hosted model providers (Claude / OpenAI) behind the gated-remote path.

The safety invariant: hosted providers are NEVER used under a local-first policy,
only under no_restriction. Also verifies provider selection by kind and that
hosted responses are labelled external_data_shared.
"""

import pytest

from buster.config import BusterConfig
from buster.models.provider import ModelInfo
from buster.models.router import ModelRouter


class _Fake:
    """Minimal provider double for the router's remote slot."""

    def __init__(self, name, reachable=True, models=None):
        self.name = name
        self._reachable = reachable
        self._models = models or ["hosted-model"]

    async def health(self):
        from buster.models.provider import ProviderHealth

        return ProviderHealth(provider=self.name, reachable=self._reachable, location="remote")

    async def list_models(self):
        return [ModelInfo(provider=self.name, name=m, inference_location="remote")
                for m in self._models]


def test_router_selects_anthropic_when_kind_anthropic():
    cfg = BusterConfig()
    cfg.inference.remote.enabled = True
    cfg.inference.remote.kind = "anthropic"
    cfg.inference.remote.api_key = "sk-ant-test"
    r = ModelRouter(cfg)
    assert r._remote is not None
    assert r._remote.name == "anthropic"


def test_router_selects_openai_compatible_when_kind_openai():
    cfg = BusterConfig()
    cfg.inference.remote.enabled = True
    cfg.inference.remote.kind = "openai_compatible"
    cfg.inference.remote.base_url = "https://api.openai.com/v1"
    cfg.inference.remote.api_key = "sk-test"
    r = ModelRouter(cfg)
    assert r._remote is not None
    assert r._remote.name == "remote"


@pytest.mark.asyncio
async def test_hosted_never_used_under_local_first():
    cfg = BusterConfig()
    cfg.inference.remote.enabled = True
    cfg.inference.remote.kind = "anthropic"
    cfg.inference.remote.api_key = "sk-ant-test"
    cfg.inference.remote.model = "claude-sonnet-4-5"
    cfg.inference.policy = "local_first_ask_external"  # forbids external
    r = ModelRouter(cfg)
    r._device = []
    r._lan = []
    r._remote = _Fake("anthropic")
    decision = await r.route()
    # Must NOT route to the hosted provider; falls back to disabled.
    assert decision.model == "none"
    assert decision.external_data_shared is False


@pytest.mark.asyncio
async def test_hosted_used_only_under_no_restriction():
    cfg = BusterConfig()
    cfg.inference.remote.enabled = True
    cfg.inference.remote.kind = "anthropic"
    cfg.inference.remote.api_key = "sk-ant-test"
    cfg.inference.remote.model = "claude-sonnet-4-5"
    cfg.inference.policy = "no_restriction"
    r = ModelRouter(cfg)
    r._device = []
    r._lan = []
    r._remote = _Fake("anthropic", models=["claude-sonnet-4-5"])
    decision = await r.route()
    assert decision.location == "remote"
    assert decision.external_data_shared is True


@pytest.mark.asyncio
async def test_anthropic_chat_labels_external():
    from buster.models.anthropic import AnthropicProvider
    from buster.models.provider import ChatMessage, ChatRequest

    prov = AnthropicProvider(api_key="sk-ant-test")

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": "hello from claude"}]}

    import httpx

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, *a, **k):
            return FakeResp()

    import buster.models.anthropic as amod

    orig = httpx.AsyncClient
    httpx.AsyncClient = FakeClient
    try:
        resp = await prov.chat(ChatRequest(
            model="claude-sonnet-4-5",
            messages=[ChatMessage(role="system", content="be brief"),
                      ChatMessage(role="user", content="hi")],
        ))
    finally:
        httpx.AsyncClient = orig
    assert resp.content == "hello from claude"
    assert resp.external_data_shared is True
    assert resp.inference_location == "remote"
