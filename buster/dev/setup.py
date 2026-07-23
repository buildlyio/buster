"""Developer setup: detect + (approved) install bb-code and tokenjam.

- bb-code (Buildly-Marketplace/bb-code): local-first codegen CLI. Buster detects
  it and registers it as a CLI runtime so `build .` plans can be launched
  through the runtime layer (P2.1). Same local/LAN Ollama tiers Buster uses.
- tokenjam (Metabuilder-Labs/tokenjam, MIT): token-efficiency telemetry, 100%
  local. Buster reads its findings READ-ONLY and credits it.

No silent installs: install_command() returns the exact command for the user to
run (or approve); Buster does not pip/pipx-install packages on its own.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

# Attribution shown in UI/CLI (per tokenjam's MIT license).
TOKENJAM_CREDIT = (
    "TokenJam — token efficiency for AI agents, 100% local. "
    "© Metabuilder-Labs (MIT). https://github.com/Metabuilder-Labs/tokenjam"
)


class DevToolStatus(BaseModel):
    key: str
    name: str
    present: bool
    path: str = ""
    version: str = ""
    install_cmd: str = ""     # command the user can run to install (if absent)
    note: str = ""


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _version(cmd: str) -> str:
    try:
        out = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return ""
        return (out.stdout or out.stderr).strip().splitlines()[0][:60]
    except Exception:  # noqa: BLE001
        return ""


def install_command(tool_key: str) -> str:
    """The supported install command for a tool (for the user to run/approve)."""
    return {
        # bb-code: install from its own ops/install.sh (see its README).
        "bb_code": "git clone https://github.com/Buildly-Marketplace/bb-code && "
                   "bb-code/ops/install.sh",
        # tokenjam: its supported install path.
        "tokenjam": "pipx install tokenjam   # or: npx tokenjam onboard",
    }.get(tool_key, "")


def dev_status() -> list[DevToolStatus]:
    """Detection of the developer tools Buster integrates with."""
    out: list[DevToolStatus] = []

    bb = _which("bb-code", "build")
    out.append(DevToolStatus(
        key="bb_code", name="bb-code (codegen)", present=bool(bb), path=bb or "",
        version=_version(bb) if bb else "",
        install_cmd="" if bb else install_command("bb_code"),
        note="Registered as a CLI runtime — 'buster runtimes'." if bb
             else "Local-first codegen; optional.",
    ))

    tj = _which("tj", "tokenjam")
    out.append(DevToolStatus(
        key="tokenjam", name="TokenJam (token telemetry)", present=bool(tj), path=tj or "",
        version=_version(tj) if tj else "",
        install_cmd="" if tj else install_command("tokenjam"),
        note=TOKENJAM_CREDIT,
    ))

    ollama = _which("ollama")
    out.append(DevToolStatus(
        key="ollama", name="Ollama (local models)", present=bool(ollama), path=ollama or "",
        note="Powers bb-code and Buster's local inference." if ollama
             else "Install to run models locally.",
    ))
    return out


class TokenjamSummary(BaseModel):
    available: bool
    credit: str = TOKENJAM_CREDIT
    findings: list[dict] = Field(default_factory=list)
    raw: str = ""
    note: str = ""


def tokenjam_summary(timeout: int = 20) -> TokenjamSummary:
    """Read-only: run `tj optimize --json` (or plain) and surface findings.

    Buster sends tokenjam nothing beyond invoking its own analysis of the user's
    local telemetry. If tokenjam isn't installed, returns available=False.
    """
    tj = _which("tj", "tokenjam")
    if not tj:
        return TokenjamSummary(available=False,
                               note="TokenJam not installed. " + install_command("tokenjam"))
    # Prefer JSON output; fall back to text.
    for args in (["optimize", "--json"], ["optimize"]):
        try:
            proc = subprocess.run([tj, *args], capture_output=True, text=True, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return TokenjamSummary(available=True, note=f"tj error: {exc}")
        out = (proc.stdout or "").strip()
        if not out:
            continue
        if "--json" in args:
            try:
                data = json.loads(out)
                findings = (data if isinstance(data, list)
                            else data.get("findings", data.get("candidates", [])))
                if isinstance(findings, list):
                    return TokenjamSummary(available=True, findings=findings[:50])
            except json.JSONDecodeError:
                pass
        return TokenjamSummary(available=True, raw=out[:4000])
    return TokenjamSummary(available=True, note="TokenJam produced no output yet — "
                           "run `tj onboard` to start capturing telemetry.")


def register_bb_code_runtime() -> dict | None:
    """If bb-code is present, register it as a CLI runtime (P2.1) so it can be
    launched/streamed through the runtime layer. Returns the runtime row, or None."""
    bb = _which("bb-code", "build")
    if not bb:
        return None
    from datetime import UTC, datetime

    from buster.database import get_database

    exe = Path(bb).name
    now = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    manifest = {
        "id": "runtime.bb-code", "runtime_type": "cli", "name": "bb-code",
        "detected_via": "cli", "capabilities": ["codegen", "task.submit"],
        "executable": exe, "argv_template": ["build", "{prompt}"],
    }
    get_database().execute(
        "INSERT INTO runtimes (id, runtime_type, name, detected_via, status, manifest, trust, "
        "discovered_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET status=excluded.status, manifest=excluded.manifest, "
        "last_seen_at=excluded.last_seen_at",
        ("runtime.bb-code", "cli", "bb-code", "cli", "detected", json.dumps(manifest),
         "detected", now, now),
    )
    return manifest
