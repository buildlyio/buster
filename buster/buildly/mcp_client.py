"""MCP client for bb-agent-manager (the Buildly MCP server).

Buster is a *client*: it connects to bb-agent-manager and calls its tools
(buildly_login, buildly_get_products, buildly_get_issues, buildly_create_*, ...).
bb-agent-manager owns all Labs calls, including OAuth. No direct Labs API code
lives in Buster.

Connection order (per the agreed model):
  1. hosted MCP over SSE  (config.buildly.mcp_url, e.g. http://bespin.home:8000/sse)
  2. local bb-agent-manager over stdio (config.buildly.mcp_local_command)

Each call opens a short-lived session (connect → initialize → call_tool → close).
This keeps Buster lightweight and avoids holding a long-lived subprocess/socket;
the cost is one connect per call, which is fine for interactive use.

Health is verified with a REAL call, because the live bespin.home server showed
that `buildly_auth_status` can report authenticated while actual Labs calls
return 401 (stale token). So we surface a distinct ``token_invalid`` state.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Any

from buster.config import load_config


class McpTransport(str, Enum):
    SSE = "sse"          # hosted, e.g. bespin.home:8000
    STDIO = "stdio"      # local buildly-mcp
    NONE = "none"


class LabsAuthState(str, Enum):
    OK = "ok"                    # a real call succeeded
    UNAUTHENTICATED = "unauthenticated"
    TOKEN_INVALID = "token_invalid"   # server says authed, Labs returns 401
    UNREACHABLE = "unreachable"       # can't reach the MCP server at all


@dataclass
class McpTarget:
    transport: McpTransport
    detail: str          # url for SSE, command for stdio


def _resolve_target() -> McpTarget:
    cfg = load_config()
    url = cfg.buildly.mcp_url.strip()
    if url:
        return McpTarget(McpTransport.SSE, url)
    cmd = cfg.buildly.mcp_local_command.strip()
    if cmd and shutil.which(cmd.split()[0]):
        return McpTarget(McpTransport.STDIO, cmd)
    return McpTarget(McpTransport.NONE, "")


class BuildlyMcpClient:
    """Thin async client over bb-agent-manager's MCP tools."""

    def __init__(self, target: McpTarget | None = None) -> None:
        self.target = target or _resolve_target()

    @property
    def available(self) -> bool:
        return self.target.transport != McpTransport.NONE

    # -- low-level -----------------------------------------------------------

    async def _call(self, tool: str, arguments: dict | None = None) -> Any:
        """Open a session, call one tool, return its parsed result."""
        from mcp import ClientSession

        if not self.available:
            raise RuntimeError(
                "No bb-agent-manager configured. Set buildly.mcp_url (hosted, e.g. "
                "http://bespin.home:8000/sse) or install the local 'buildly-mcp'."
            )
        if self.target.transport == McpTransport.SSE:
            from mcp.client.sse import sse_client

            async with sse_client(self.target.detail) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return _parse(await session.call_tool(tool, arguments or {}))
        else:
            from mcp.client.stdio import StdioServerParameters, stdio_client

            parts = self.target.detail.split()
            params = StdioServerParameters(command=parts[0], args=parts[1:])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return _parse(await session.call_tool(tool, arguments or {}))

    async def list_tools(self) -> list[str]:
        from mcp import ClientSession

        if not self.available:
            return []
        if self.target.transport == McpTransport.SSE:
            from mcp.client.sse import sse_client

            async with sse_client(self.target.detail) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    resp = await session.list_tools()
                    return [t.name for t in resp.tools]
        from mcp.client.stdio import StdioServerParameters, stdio_client

        parts = self.target.detail.split()
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
                return [t.name for t in resp.tools]

    # -- high-level Labs operations ------------------------------------------

    async def auth_state(self) -> LabsAuthState:
        """Verify auth with a REAL call, not just buildly_auth_status."""
        try:
            status = await self._call("buildly_auth_status")
        except Exception:  # noqa: BLE001
            return LabsAuthState.UNREACHABLE
        if not (isinstance(status, dict) and status.get("authenticated")):
            return LabsAuthState.UNAUTHENTICATED
        # Authenticated per the server — confirm with a real Labs read.
        try:
            probe = await self._call("buildly_get_products", {"limit": 1})
        except Exception:  # noqa: BLE001
            return LabsAuthState.UNREACHABLE
        if isinstance(probe, dict) and str(probe.get("error", "")).startswith("HTTP 401"):
            return LabsAuthState.TOKEN_INVALID
        return LabsAuthState.OK

    async def login(self, api_token: str | None = None) -> dict:
        args = {"api_token": api_token} if api_token else {}
        return await self._call("buildly_login", args)

    async def logout(self) -> dict:
        return await self._call("buildly_logout")

    async def products(self, limit: int = 50) -> list[dict]:
        res = await self._call("buildly_get_products", {"limit": limit})
        return _items(res)

    async def issues(self, product_id: str | None = None, status: str | None = None,
                     limit: int = 50) -> list[dict]:
        args: dict = {"limit": limit}
        if product_id:
            args["product_id"] = product_id
        if status:
            args["status"] = status
        return _items(await self._call("buildly_get_issues", args))

    async def create_issue(self, product_id: str, name: str, description: str = "") -> dict:
        return await self._call("buildly_create_issue", {
            "product_id": product_id, "name": name, "description": description})

    async def create_task(self, product_id: str, name: str, description: str = "",
                          parent_uuid: str | None = None) -> dict:
        args = {"product_id": product_id, "name": name, "description": description}
        if parent_uuid:
            args["parent_uuid"] = parent_uuid
        return await self._call("buildly_create_task", args)

    async def create_product(self, name: str, description: str = "") -> dict:
        return await self._call("buildly_create_product", {
            "name": name, "description": description})


def _parse(result: Any) -> Any:
    """Extract the JSON/text payload from an MCP CallToolResult."""
    content = getattr(result, "content", None)
    if not content:
        return {}
    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"text": text}


def _items(res: Any) -> list[dict]:
    """Normalize a get_* result into a list of dict items."""
    if isinstance(res, dict):
        data = res.get("data", res)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):
            for key in ("results", "items", "products", "backlog", "tasks", "data"):
                v = data.get(key)
                if isinstance(v, list):
                    return [d for d in v if isinstance(d, dict)]
    return []


def get_mcp_client() -> BuildlyMcpClient:
    return BuildlyMcpClient()
