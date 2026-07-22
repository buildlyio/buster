"""Detect Buildly / developer tools on this machine.

Read-only PATH + filesystem checks. Used to decide whether to offer Buster's
developer profile. Buster never installs or runs these — it only notices them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel


class DevTool(BaseModel):
    key: str
    name: str
    present: bool
    kind: str            # buildly | vcs | model | editor
    detail: str = ""


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def detect_dev_tools() -> list[DevTool]:
    tools: list[DevTool] = []

    # Buildly tools.
    bb_agent = _which("bb-agent-manager", "buildly-agent")
    tools.append(DevTool(key="bb_agent_manager", name="Buildly MCP (bb-agent-manager)",
                         present=bool(bb_agent), kind="buildly", detail=bb_agent or ""))
    bb_code = _which("bb-code", "build")
    tools.append(DevTool(key="bb_code", name="bb-code", present=bool(bb_code),
                         kind="buildly", detail=bb_code or ""))
    buildly_cli = _which("buildly")
    tools.append(DevTool(key="buildly_cli", name="Buildly CLI", present=bool(buildly_cli),
                         kind="buildly", detail=buildly_cli or ""))
    # A local Buildly checkout is also a signal.
    labs = Path.home() / "Projects" / "buildly"
    tools.append(DevTool(key="buildly_checkout", name="Buildly project directory",
                         present=labs.exists(), kind="buildly",
                         detail=str(labs) if labs.exists() else ""))

    # Version control + editors (dev signals).
    git = _which("git")
    tools.append(DevTool(key="git", name="git", present=bool(git), kind="vcs", detail=git or ""))
    tools.append(DevTool(key="gh", name="GitHub CLI", present=bool(_which("gh")), kind="vcs"))
    tools.append(DevTool(key="editor", name="VS Code / editor",
                         present=bool(_which("code", "cursor", "nvim", "vim")), kind="editor"))

    return tools


def buildly_tool_count(tools: list[DevTool] | None = None) -> int:
    tools = tools or detect_dev_tools()
    return sum(1 for t in tools if t.kind == "buildly" and t.present)


def dev_signal_count(tools: list[DevTool] | None = None) -> int:
    tools = tools or detect_dev_tools()
    return sum(1 for t in tools if t.present)


def should_offer_developer_profile(tools: list[DevTool] | None = None) -> bool:
    """Offer the developer profile when there's a Buildly tool present, or a
    generally dev-heavy machine (git + editor + ...)."""
    tools = tools or detect_dev_tools()
    return buildly_tool_count(tools) >= 1 or dev_signal_count(tools) >= 3
