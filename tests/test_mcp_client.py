"""Buster's MCP client to bb-agent-manager + repo↔product association.

MCP calls are mocked — no live server. Covers transport resolution, the
distinct auth states (esp. token_invalid), item normalization, and the
suggest-confirm association matching + binding write.
"""

import pytest

from buster.buildly import associate
from buster.buildly.mcp_client import (
    BuildlyMcpClient,
    LabsAuthState,
    McpTarget,
    McpTransport,
    _items,
    _resolve_target,
)


def _client_with(monkeypatch, responses: dict):
    """Build a client whose _call returns canned responses per tool name."""
    target = McpTarget(McpTransport.SSE, "http://test/sse")
    client = BuildlyMcpClient(target)

    async def fake_call(tool, arguments=None):
        val = responses.get(tool)
        if isinstance(val, Exception):
            raise val
        return val

    monkeypatch.setattr(client, "_call", fake_call)
    return client


@pytest.mark.asyncio
async def test_auth_state_ok(monkeypatch):
    client = _client_with(monkeypatch, {
        "buildly_auth_status": {"authenticated": True},
        "buildly_get_products": {"status": "ok", "data": [{"id": "p1", "name": "P"}]},
    })
    assert await client.auth_state() == LabsAuthState.OK


@pytest.mark.asyncio
async def test_auth_state_token_invalid(monkeypatch):
    # Server says authenticated, but the real Labs call 401s (stale token).
    client = _client_with(monkeypatch, {
        "buildly_auth_status": {"authenticated": True},
        "buildly_get_products": {"error": "HTTP 401", "detail": "Invalid access token"},
    })
    assert await client.auth_state() == LabsAuthState.TOKEN_INVALID


@pytest.mark.asyncio
async def test_auth_state_unauthenticated(monkeypatch):
    client = _client_with(monkeypatch, {"buildly_auth_status": {"authenticated": False}})
    assert await client.auth_state() == LabsAuthState.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_auth_state_unreachable(monkeypatch):
    client = _client_with(monkeypatch, {"buildly_auth_status": RuntimeError("no route")})
    assert await client.auth_state() == LabsAuthState.UNREACHABLE


@pytest.mark.asyncio
async def test_products_normalizes_items(monkeypatch):
    client = _client_with(monkeypatch, {
        "buildly_get_products": {"status": "ok", "data": {"results": [
            {"id": "p1", "name": "Alpha"}, {"id": "p2", "name": "Beta"}]}},
    })
    products = await client.products()
    assert [p["name"] for p in products] == ["Alpha", "Beta"]


def test_items_normalization_variants():
    assert _items({"data": [{"a": 1}]}) == [{"a": 1}]
    assert _items({"data": {"backlog": [{"b": 2}]}}) == [{"b": 2}]
    assert _items({"error": "HTTP 401"}) == []


def test_resolve_target_prefers_configured_url(monkeypatch):
    from buster.config import load_config, save_config

    cfg = load_config()
    cfg.buildly.mcp_url = "http://host/sse"
    save_config(cfg)
    t = _resolve_target()
    assert t.transport == McpTransport.SSE and t.detail == "http://host/sse"


def test_resolve_target_none_when_nothing(monkeypatch):
    from buster.config import load_config, save_config

    cfg = load_config()
    cfg.buildly.mcp_url = ""
    cfg.buildly.mcp_local_command = "definitely-not-installed-xyz"
    save_config(cfg)
    assert _resolve_target().transport == McpTransport.NONE


def test_suggest_matches_exact_and_fuzzy(tmp_path):
    repo = tmp_path / "inventory-service"
    repo.mkdir()
    products = [
        {"id": "p1", "name": "Inventory Service"},   # exact slug match
        {"id": "p2", "name": "Billing"},             # unrelated
    ]
    matches = associate.suggest_matches(str(repo), products)
    assert matches[0].product_id == "p1"
    assert matches[0].score == 1.0
    assert "exact" in matches[0].reason


def test_write_binding_creates_project_yaml(tmp_path):
    path = associate.write_binding(str(tmp_path), "p1", "Alpha", "https://labs")
    assert path.exists()
    import yaml

    data = yaml.safe_load(path.read_text())
    assert data["product_id"] == "p1" and data["product_name"] == "Alpha"
