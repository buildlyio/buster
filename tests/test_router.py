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
    r._device = [_FakeProvider(True, ["gemma3:latest"], "device")]
    r._lan = [_FakeProvider(True, ["qwen2.5:7b"], "lan")]
    d = await r.route()
    assert d.location == "device"
    assert d.external_data_shared is False


@pytest.mark.asyncio
async def test_falls_back_to_lan_when_no_local_model(monkeypatch):
    cfg = BusterConfig()
    r = ModelRouter(cfg)
    r._device = [_FakeProvider(False, [], "device")]
    r._lan = [_FakeProvider(True, ["qwen2.5:7b"], "lan")]
    d = await r.route()
    assert d.location == "lan"
    assert d.model == "qwen2.5:7b"
    assert d.external_data_shared is False  # LAN is still local network


@pytest.mark.asyncio
async def test_disabled_when_nothing_available():
    cfg = BusterConfig()
    r = ModelRouter(cfg)
    r._device = [_FakeProvider(False, [], "device")]
    r._lan = []
    d = await r.route()
    assert d.model == "none"
    assert d.provider.name == "disabled"


@pytest.mark.asyncio
async def test_embedding_model_not_default():
    cfg = BusterConfig()
    r = ModelRouter(cfg)
    r._device = [_FakeProvider(True, ["nomic-embed-text", "gemma3:latest"], "device")]
    r._lan = []
    d = await r.route()
    assert d.model == "gemma3:latest"


@pytest.mark.asyncio
async def test_remote_not_used_under_local_first_policy():
    """A configured remote provider must NOT be used unless policy allows external."""
    cfg = BusterConfig()
    cfg.inference.remote.enabled = True
    cfg.inference.remote.base_url = "https://example.com/v1"
    cfg.inference.remote.model = "some-model"
    cfg.inference.policy = "local_first_ask_external"  # forbids auto external
    r = ModelRouter(cfg)
    r._device = [_FakeProvider(False, [], "device")]
    r._lan = []
    d = await r.route()
    # Remote is configured but policy forbids it → disabled, no data shared.
    assert d.model == "none"
    assert d.external_data_shared is False


@pytest.mark.asyncio
async def test_remote_used_only_when_policy_permits():
    cfg = BusterConfig()
    cfg.inference.remote.enabled = True
    cfg.inference.remote.base_url = "https://example.com/v1"
    cfg.inference.remote.model = "some-model"
    cfg.inference.policy = "no_restriction"
    r = ModelRouter(cfg)
    r._device = [_FakeProvider(False, [], "device")]
    r._lan = []
    r._remote = _FakeProvider(True, ["some-model"], "remote")
    d = await r.route()
    assert d.location == "remote"
    assert d.external_data_shared is True
