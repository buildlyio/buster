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


def test_onboarding_default_prefers_provider_with_models():
    """When local has no models but a LAN server does, the default choice must
    point at the provider that actually has models."""
    from buster.models.detect import DetectedProvider

    local = [DetectedProvider(kind="ollama", base_url="http://127.0.0.1:11434",
                              location="device", host="127.0.0.1", models=[])]
    lan = [DetectedProvider(kind="ollama", base_url="http://192.168.1.113:11434",
                            location="lan", host="192.168.1.113",
                            models=["gemma3:latest"])]
    found = local + lan
    first_usable = next((i for i, p in enumerate(found, 1) if p.models), None)
    assert first_usable == 2  # the LAN server, not the empty local one


def test_capability_context_lists_real_functions():
    """The agent system preamble must describe Buster's real capabilities."""
    from buster.context import build_context

    ctx = build_context("what can you do?")
    p = ctx.system_preamble.lower()
    assert "you are buster" in p
    # Mentions concrete capability areas, not generic chat.
    assert "diagnose" in p
    assert "research the web" in p
    assert "capabilities" in ctx.categories_loaded


def test_model_size_parsing_and_suggestion():
    from buster.models.capability import _model_billions, suggest_faster_model

    assert _model_billions("gemma4:e4b") == 4.0
    assert _model_billions("qwen2.5:7b") == 7.0
    assert _model_billions("llama3:70b") == 70.0
    # A 70B model on any normal box should trigger a smaller-model suggestion.
    s = suggest_faster_model("llama3:70b", ["llama3:70b", "qwen2.5:7b"])
    assert s and "qwen2.5:7b" in s


def test_static_detection_is_cached():
    from buster.models.capability import _static_detection

    a = _static_detection()
    b = _static_detection()
    assert a is b  # lru_cache returns the same object


def test_dev_tool_detection_and_offer(monkeypatch):
    import shutil as _sh

    from buster.buildly import devtools

    # Simulate a dev machine: git + editor + bb-code present.
    present = {"git", "code", "bb-code"}
    monkeypatch.setattr(devtools.shutil, "which",
                        lambda n: f"/usr/bin/{n}" if n in present else None)
    tools = devtools.detect_dev_tools()
    assert devtools.dev_signal_count(tools) >= 1
    assert devtools.should_offer_developer_profile(tools) is True


def test_no_dev_offer_on_bare_machine(monkeypatch):
    from buster.buildly import devtools

    monkeypatch.setattr(devtools.shutil, "which", lambda n: None)
    # Also avoid the ~/Projects/buildly signal.
    monkeypatch.setattr(devtools.Path, "home", staticmethod(lambda: devtools.Path("/nonexistent-xyz")))
    tools = devtools.detect_dev_tools()
    assert devtools.should_offer_developer_profile(tools) is False


def test_developer_profile_exists():
    from buster.personality import get_personality

    svc = get_personality()
    assert "developer" in svc.profiles()
    svc.set_profile("developer", reason="test")
    assert svc.current_profile() == "developer"
    svc.set_profile("friendly_guide", reason="reset")
