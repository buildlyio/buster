"""Dev workflow Phase 3: Start Work → context package → agent run → review.

Buster coordinates: it assembles a bounded context package (excluding secrets),
lets the user pick an agent, runs it through the GATED runtime submit path
(P2.1 — off by default, risk-2 approval for real runtimes, data-only results),
records the run for audit, and produces a change manifest for human review.

Runs are persisted under .buildly/work/ as Git-trackable JSON so the history
survives restart and is reviewable.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from buster.buildly.protocol import AgentRun, ChangeManifest, ContextPackage, IssueContract

_WORK_DIR = ".buildly/work"
# Never include these in a context package handed to an agent.
_SECRET_NAMES = {".env", ".env.local", "secrets.yaml", "secrets.yml", "credentials.json"}
_SECRET_SUFFIXES = (".pem", ".key")
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".buildly"}


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _sid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _is_secret(rel: str) -> bool:
    name = Path(rel).name.lower()
    return name in _SECRET_NAMES or name.endswith(_SECRET_SUFFIXES) or "secret" in name


class WorkStore:
    """Per-repo store for context packages, agent runs, and change manifests."""

    def __init__(self, repo_path: str) -> None:
        self.repo = Path(repo_path).expanduser()
        self.dir = self.repo / _WORK_DIR

    def _write(self, subdir: str, obj_id: str, data: dict) -> Path:
        d = self.dir / subdir
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{obj_id}.json"
        path.write_text(json.dumps(data, indent=2))
        return path

    def _read_all(self, subdir: str) -> list[dict]:
        d = self.dir / subdir
        if not d.exists():
            return []
        out = []
        for f in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(f.read_text()))
            except Exception:  # noqa: BLE001
                continue
        return out

    # -- context package -----------------------------------------------------

    def build_context_package(self, issue: IssueContract, max_files: int = 25) -> ContextPackage:
        """Assemble a bounded context package for an issue. Excludes secrets and
        skipped dirs; relevance is a simple keyword match on the issue text."""
        keywords = set()
        for text in [issue.title, issue.intent, *issue.likely_components]:
            keywords.update(w.lower() for w in text.replace("/", " ").split() if len(w) > 3)

        included: list[str] = []
        secrets_excluded = 0
        for f in self.repo.rglob("*"):
            if not f.is_file():
                continue
            rel = str(f.relative_to(self.repo))
            if any(part in _SKIP_DIRS for part in Path(rel).parts):
                continue
            if _is_secret(rel):
                secrets_excluded += 1
                continue
            if f.suffix not in (".py", ".js", ".ts", ".tsx", ".go", ".md", ".yaml", ".yml"):
                continue
            # Relevance: keyword hit in path, or (fallback) any source file.
            low = rel.lower()
            if not keywords or any(k in low for k in keywords):
                included.append(rel)
            if len(included) >= max_files:
                break
        if not included:  # fallback: a few source files so the package isn't empty
            for f in self.repo.rglob("*.py"):
                rel = f.relative_to(self.repo)
                if not any(p in _SKIP_DIRS for p in rel.parts):
                    included.append(str(rel))
                if len(included) >= max_files:
                    break

        pkg = ContextPackage(
            id=_sid("ctx"), issue_id=issue.id,
            summary=f"Bounded context for {issue.id}: {issue.title}",
            included_files=included,
            excluded_note=(f"Secrets ({secrets_excluded} file(s)), .env, keys, and "
                           f"{'/'.join(sorted(_SKIP_DIRS))} excluded."),
            token_estimate=sum(len(c) for c in included) // 4 + 200,
            engine="buster-local",
        )
        self._write("context", pkg.id, pkg.model_dump())
        return pkg

    def get_context_package(self, ctx_id: str) -> ContextPackage | None:
        path = self.dir / "context" / f"{ctx_id}.json"
        if not path.exists():
            return None
        return ContextPackage.model_validate_json(path.read_text())

    # -- agent runs ----------------------------------------------------------

    def record_run(self, run: AgentRun) -> AgentRun:
        self._write("runs", run.id, run.model_dump())
        return run

    def list_runs(self) -> list[dict]:
        return self._read_all("runs")

    # -- change manifests ----------------------------------------------------

    def save_manifest(self, manifest: ChangeManifest) -> ChangeManifest:
        self._write("manifests", manifest.id, manifest.model_dump())
        return manifest

    def list_manifests(self) -> list[dict]:
        return self._read_all("manifests")


def issue_from_labs(item: dict) -> IssueContract:
    """Adapt a Labs backlog item into an IssueContract for work context."""
    return IssueContract(
        id=str(item.get("id") or item.get("uuid") or _sid("iss")),
        title=str(item.get("name") or item.get("title") or "Untitled"),
        source="labs",
        intent=str(item.get("description", "")),
    )
