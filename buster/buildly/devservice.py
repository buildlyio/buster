"""BuildlyDevelopmentService — Buster's coordinator interface for the AI-Native
product-development workflow.

Buster owns the UX and local continuity; the heavy engines (adoption scan,
context packages, change manifests, validation, Labs sync, conflict detection)
belong to bb-agent-manager / a shared protocol package. This module defines the
abstraction and a MOCK implementation so the UX and tests work before those
engines exist. A real MCP-backed implementation plugs in behind the same
Protocol later.

Boundaries enforced here (from the spec):
  * Repository inspection is local + read-only (legitimately Buster-owned).
  * The adoption scan NEVER modifies production files — the mock only writes
    under .buildly/adoption/ and devdocs/generated/.
  * Inferred statements are never auto-approved.
  * Labs connectivity is never required for local operation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

from buster.buildly.protocol import (
    AdoptionReport,
    ChangeManifest,
    ContextPackage,
    ProductBinding,
    RepositoryContext,
    SyncConflict,
    SyncStatus,
)


@runtime_checkable
class BuildlyDevelopmentService(Protocol):
    async def inspect_repository(self, path: str) -> RepositoryContext: ...
    async def get_binding(self, path: str) -> ProductBinding: ...
    async def connect_product(self, path: str, product_id: str) -> ProductBinding: ...
    async def scan_repository(self, path: str) -> AdoptionReport: ...
    async def get_adoption_report(self, path: str) -> AdoptionReport | None: ...
    async def generate_documentation(self, path: str) -> list[str]: ...
    async def generate_diagrams(self, path: str) -> list[str]: ...
    async def create_context_package(self, path: str, issue_id: str) -> ContextPackage: ...
    async def get_sync_status(self, path: str) -> SyncStatus: ...
    async def list_conflicts(self, path: str) -> list[SyncConflict]: ...
    async def create_change_manifest(self, path: str, run_id: str) -> ChangeManifest: ...


# -- repository inspection (real, local, read-only) --------------------------

def _run_git(path: str, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", path, *args], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _detect_framework(path: str) -> tuple[str, list[str]]:
    """Best-effort framework + languages from marker files. Read-only."""
    p = Path(path)
    langs: set[str] = set()
    framework = ""

    def has(*names: str) -> bool:
        return any((p / n).exists() for n in names)

    def read(name: str) -> str:
        f = p / name
        try:
            return f.read_text(errors="ignore") if f.exists() else ""
        except OSError:
            return ""

    if has("pyproject.toml", "requirements.txt", "setup.py"):
        langs.add("python")
        blob = read("pyproject.toml") + read("requirements.txt")
        low = blob.lower()
        if "fastapi" in low:
            framework = "fastapi"
        elif "django" in low:
            framework = "django"
        elif "flask" in low:
            framework = "flask"
    if has("package.json"):
        langs.add("javascript")
        pkg = read("package.json").lower()
        if "react" in pkg:
            framework = framework or "react"
        elif "next" in pkg:
            framework = framework or "next"
        elif "vue" in pkg:
            framework = framework or "vue"
        elif "express" in pkg:
            framework = framework or "express"
    if has("go.mod"):
        langs.add("go")
    if has("Cargo.toml"):
        langs.add("rust")
    return framework, sorted(langs)


def _detect_topology(path: str) -> str:
    p = Path(path)
    # crude: multiple package.json / pyproject under subdirs → monorepo
    markers = list(p.glob("*/package.json")) + list(p.glob("*/pyproject.toml"))
    if len(markers) >= 2:
        return "monorepo"
    return "single"


def inspect_repository_local(path: str) -> RepositoryContext:
    p = Path(path).expanduser()
    is_git = (p / ".git").exists() or bool(_run_git(str(p), "rev-parse", "--is-inside-work-tree"))
    default_branch = ""
    current_branch = ""
    if is_git:
        current_branch = _run_git(str(p), "rev-parse", "--abbrev-ref", "HEAD")
        head = _run_git(str(p), "symbolic-ref", "refs/remotes/origin/HEAD")
        default_branch = head.rsplit("/", 1)[-1] if head else current_branch
    framework, langs = _detect_framework(str(p))
    return RepositoryContext(
        path=str(p),
        is_git=is_git,
        default_branch=default_branch,
        current_branch=current_branch,
        framework=framework,
        languages=langs,
        topology=_detect_topology(str(p)),
        has_buildly_project=(p / ".buildly" / "project.yaml").exists(),
        has_local_memory=(p / "buildly_memory").exists(),
        has_pending_sync=(p / ".buildly" / "sync" / "pending").exists(),
    )
