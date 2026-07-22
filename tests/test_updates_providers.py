"""Tests for update-checking, provider detection, and the LM Studio adapter."""

import pytest

from buster.updates import is_newer


def test_version_comparison():
    assert is_newer("0.2.0", "0.1.0")
    assert is_newer("v0.1.1", "0.1.0")
    assert not is_newer("0.1.0", "0.1.0")
    assert not is_newer("0.1.0", "0.2.0")
    assert is_newer("1.0.0", "0.9.9")


@pytest.mark.asyncio
async def test_check_for_update_cached(monkeypatch):
    from buster import updates

    calls = {"n": 0}

    async def fake_latest():
        calls["n"] += 1
        return "v9.9.9"

    monkeypatch.setattr(updates, "latest_release", fake_latest)
    a = await updates.check_for_update(force=True)
    assert a["available"] is True
    assert a["latest"] == "v9.9.9"
    # Second call (not forced) should hit the cache, not the network.
    b = await updates.check_for_update()
    assert b == a
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_check_for_update_handles_offline(monkeypatch):
    from buster import updates

    async def fake_latest():
        return None

    monkeypatch.setattr(updates, "latest_release", fake_latest)
    info = await updates.check_for_update(force=True)
    assert info["latest"] is None
    assert info["available"] is False


@pytest.mark.asyncio
async def test_detect_local_no_servers(monkeypatch):
    """With nothing listening, detection returns an empty list (no crash)."""
    from buster.models import detect

    async def none(*a, **k):
        return None

    monkeypatch.setattr(detect, "_probe_ollama", none)
    monkeypatch.setattr(detect, "_probe_lmstudio", none)
    assert await detect.detect_local() == []


@pytest.mark.asyncio
async def test_detect_lan_requires_optin():
    """LAN scan must not run unless explicitly requested."""
    from buster.models import detect

    assert await detect.detect_lan(scan=False) == []


def test_lmstudio_provider_shape():
    from buster.models.lmstudio import OpenAICompatibleProvider

    p = OpenAICompatibleProvider("http://127.0.0.1:1234/v1", location="device")
    assert p.name == "lmstudio"
    assert p.base_url == "http://127.0.0.1:1234/v1"
    # api key header only when set
    assert "Authorization" not in p._headers()
    p2 = OpenAICompatibleProvider("http://x/v1", api_key="sk-x")
    assert p2._headers()["Authorization"] == "Bearer sk-x"


def test_ascii_rabbit_is_pure_ascii():
    from buster.cli import art

    # The CLI art must be pure ASCII so it renders in any terminal.
    art.RABBIT.encode("ascii")
    art.RABBIT_LARGE.encode("ascii")
    assert "buildly.io" in art.TAGLINE
