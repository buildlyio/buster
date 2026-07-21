import pytest

from buster.config import BusterConfig
from buster.models.router import ModelRouter
from buster.models.provider import ModelInfo


class _FakeProvider:
    name = "ollama"

    def __init__(self, reachable, models, location="device"):
        self._reachable = reachable
        self._models = models
        self.location = location

    async def health(self):
        from buster.models.provider import ProviderHealth
        return ProviderHealth(provider=self.name, reachable=self._reachable, location=self.location)

    async def list_models(self):
        return [ModelInfo(provider="ollama", name=m, inference_location=self.location) for m in self._models]


@pytest.mark.asyncio
async def test_prefers_local(monkeypatch):
    cfg = BusterConfig()
    r = ModelRouter(cfg)
    r._local = _FakeProvider(True, ["gemma3:latest"], "device")
    r._lan = [_FakeProvider(True, ["qwen2.5:7b"], "lan")]
    d = await r.route()
    assert d.location == "device"
    assert d.external_data_shared is False


@pytest.mark.asyncio
async def test_falls_back_to_lan_when_no_local_model(monkeypatch):
    cfg = BusterConfig()
    r = ModelRouter(cfg)
    r._local = _FakeProvider(False, [], "device")
    r._lan = [_FakeProvider(True, ["qwen2.5:7b"], "lan")]
    d = await r.route()
    assert d.location == "lan"
    assert d.model == "qwen2.5:7b"
    assert d.external_data_shared is False  # LAN is still local network


@pytest.mark.asyncio
async def test_disabled_when_nothing_available():
    cfg = BusterConfig()
    r = ModelRouter(cfg)
    r._local = _FakeProvider(False, [], "device")
    r._lan = []
    d = await r.route()
    assert d.model == "none"
    assert d.provider.name == "disabled"


@pytest.mark.asyncio
async def test_embedding_model_not_default():
    cfg = BusterConfig()
    r = ModelRouter(cfg)
    r._local = _FakeProvider(True, ["nomic-embed-text", "gemma3:latest"], "device")
    r._lan = []
    d = await r.route()
    assert d.model == "gemma3:latest"
