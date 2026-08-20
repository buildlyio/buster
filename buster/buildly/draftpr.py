"""Draft pull-request preparation (Phase 4).

Buster PREPARES a draft PR but NEVER merges (spec non-negotiable). Preparation
is conservative and explicit:
  1. Create a work branch (if not already on one).
  2. Optionally commit currently-staged changes with a message.
  3. Optionally push the branch.
  4. Optionally open a DRAFT PR via `gh` (if installed + authenticated).

Every step is opt-in via flags; by default it only computes what WOULD happen
(a plan) so the caller can confirm. Auto-merge is impossible here — there is no
merge path in this module at all.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field


class DraftPRPlan(BaseModel):
    repo: str
    current_branch: str = ""
    proposed_branch: str = ""
    changed_files: list[str] = Field(default_factory=list)
    has_changes: bool = False
    steps: list[str] = Field(default_factory=list)      # human-readable plan
    warnings: list[str] = Field(default_factory=list)


class DraftPRResult(BaseModel):
    ok: bool
    branch: str = ""
    committed: bool = False
    pushed: bool = False
    pr_url: str = ""
    detail: str = ""
    merged: bool = False        # ALWAYS False — Buster never merges.


def _git(repo: str, *args: str, timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _current_branch(repo: str) -> str:
    _, out = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return out


def _changed_files(repo: str) -> list[str]:
    _, out = _git(repo, "status", "--porcelain")
    return [ln[3:] for ln in out.splitlines() if ln.strip()]


def plan_draft_pr(repo: str, *, branch: str = "", run_id: str = "") -> DraftPRPlan:
    """Describe what preparing a draft PR would do. No side effects."""
    repo = str(Path(repo).expanduser())
    cur = _current_branch(repo)
    changed = _changed_files(repo)
    proposed = branch or (f"buster/work-{run_id}" if run_id else "buster/work")
    steps = []
    warnings = []
    if not (Path(repo) / ".git").exists() and cur == "":
        warnings.append("Not a git repository — cannot prepare a PR.")
    if cur == proposed:
        steps.append(f"Already on '{proposed}'.")
    else:
        steps.append(f"Create/switch to branch '{proposed}'.")
    if changed:
        steps.append(f"Commit {len(changed)} changed file(s).")
    else:
        warnings.append("No changes to commit.")
    steps.append("Push the branch.")
    steps.append("Open a DRAFT pull request (gh). Buster never merges it.")
    return DraftPRPlan(repo=repo, current_branch=cur, proposed_branch=proposed,
                       changed_files=changed, has_changes=bool(changed),
                       steps=steps, warnings=warnings)


def prepare_draft_pr(
    repo: str, *, branch: str = "", run_id: str = "", title: str = "",
    body: str = "", commit: bool = False, push: bool = False, open_pr: bool = False,
) -> DraftPRResult:
    """Prepare a draft PR. Steps are gated by flags; NEVER merges.

    With no flags this is a dry run (returns the current state). commit/push/
    open_pr progressively do more, each explicitly requested by the caller.
    """
    repo = str(Path(repo).expanduser())
    if not (Path(repo) / ".git").exists():
        return DraftPRResult(ok=False, detail="Not a git repository.")

    proposed = branch or (f"buster/work-{run_id}" if run_id else "buster/work")
    cur = _current_branch(repo)
    result = DraftPRResult(ok=True, branch=proposed)

    # 1. branch
    if cur != proposed:
        rc, out = _git(repo, "checkout", "-B", proposed)
        if rc != 0:
            return DraftPRResult(ok=False, branch=proposed, detail=f"branch failed: {out}")

    # 2. commit (opt-in)
    if commit:
        if not _changed_files(repo):
            result.detail = "nothing to commit"
        else:
            _git(repo, "add", "-A")
            msg = title or f"Buster: prepare work {run_id}".strip()
            rc, out = _git(repo, "commit", "-m", msg)
            result.committed = rc == 0
            if rc != 0:
                result.detail = f"commit note: {out[:120]}"

    # 3. push (opt-in)
    if push:
        rc, out = _git(repo, "push", "-u", "origin", proposed)
        result.pushed = rc == 0
        if rc != 0:
            result.detail = f"push failed: {out[:160]}"
            return result

    # 4. open DRAFT PR via gh (opt-in). Never merges.
    if open_pr and result.pushed:
        import shutil

        if not shutil.which("gh"):
            result.detail = "pushed; install GitHub CLI (gh) to open the draft PR."
            return result
        try:
            p = subprocess.run(
                ["gh", "pr", "create", "--draft", "--title", title or f"Buster work {run_id}",
                 "--body", body or "Draft PR prepared by Buster. Review required; not merged."],
                cwd=repo, capture_output=True, text=True, timeout=40)
            if p.returncode == 0:
                result.pr_url = (p.stdout or "").strip().splitlines()[-1]
                result.detail = "draft PR opened (not merged)"
            else:
                result.detail = f"gh pr create note: {(p.stderr or '')[:160]}"
        except Exception as exc:  # noqa: BLE001
            result.detail = f"gh error: {exc}"

    # merged stays False, always.
    return result
