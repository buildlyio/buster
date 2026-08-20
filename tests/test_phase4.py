"""Dev workflow Phase 4 — conflict resolution, draft PR (never merges), enforcement."""

import subprocess

import pytest

from buster.buildly import draftpr, enforcement
from buster.buildly.protocol import SyncState
from buster.buildly.sync import SyncJournal


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.co"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    (tmp_path / "a.py").write_text("x=1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    return tmp_path


# -- conflict resolution ------------------------------------------------------

def test_resolve_conflict_records_new_event_no_overwrite(tmp_path):
    j = SyncJournal(str(tmp_path))
    evt = j.record("issue.create", {"name": "x", "product_id": "p1"})
    j._move(evt, SyncState.CONFLICT)
    assert j.status().conflicts == 1

    decision = j.resolve_conflict(evt.id, "keep_local")
    assert decision is not None and decision.kind == "conflict.resolved"
    st = j.status()
    assert st.conflicts == 0            # cleared
    assert st.applied == 1              # original archived, not deleted
    # keep_local re-queued the original + the decision event → 2 pending.
    assert st.pending == 2


def test_resolve_conflict_defer_keeps_it(tmp_path):
    j = SyncJournal(str(tmp_path))
    evt = j.record("issue.create", {"name": "y"})
    j._move(evt, SyncState.CONFLICT)
    j.resolve_conflict(evt.id, "defer")
    # Deferred → conflict stays; only a decision event is recorded.
    assert j.status().conflicts == 1


def test_resolve_unknown_conflict_returns_none(tmp_path):
    assert SyncJournal(str(tmp_path)).resolve_conflict("nope", "keep_local") is None


# -- draft PR (never merges) --------------------------------------------------

def test_draft_pr_plan_is_dry_run(git_repo):
    (git_repo / "feature.py").write_text("y=2\n")
    plan = draftpr.plan_draft_pr(str(git_repo), run_id="r1")
    assert plan.proposed_branch == "buster/work-r1"
    assert plan.has_changes and "feature.py" in plan.changed_files
    # dry run makes no branch
    cur = subprocess.run(["git", "-C", str(git_repo), "rev-parse", "--abbrev-ref", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    assert cur in ("main", "master")


def test_draft_pr_prepare_commits_never_merges(git_repo):
    (git_repo / "feature.py").write_text("y=2\n")
    res = draftpr.prepare_draft_pr(str(git_repo), run_id="r1", title="Add feature",
                                   commit=True, push=False, open_pr=False)
    assert res.ok and res.committed is True
    assert res.merged is False           # structurally always False
    assert res.branch == "buster/work-r1"
    cur = subprocess.run(["git", "-C", str(git_repo), "rev-parse", "--abbrev-ref", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    assert cur == "buster/work-r1"


def test_draft_pr_non_git_dir(tmp_path):
    res = draftpr.prepare_draft_pr(str(tmp_path))
    assert res.ok is False and "not a git" in res.detail.lower()


# -- progressive enforcement --------------------------------------------------

def test_enforcement_defaults_to_observe(tmp_path):
    assert enforcement.get_enforcement(str(tmp_path))["mode"] == "observe"


def test_enforcement_set_and_policy(tmp_path):
    res = enforcement.set_enforcement(str(tmp_path), "enforce_new_work")
    assert res["ok"] and res["mode"] == "enforce_new_work"
    assert res["policy"]["documentation"]["new_code"] == "require"
    assert res["policy"]["architecture"]["existing_violations"] == "baseline"
    # Persisted + reloads.
    assert enforcement.get_enforcement(str(tmp_path))["mode"] == "enforce_new_work"
    assert (tmp_path / ".buildly" / "enforcement.yaml").exists()


def test_enforcement_full_requires_everything(tmp_path):
    res = enforcement.set_enforcement(str(tmp_path), "full_enforcement")
    p = res["policy"]
    assert p["documentation"]["existing_code"] == "require"
    assert p["architecture"]["new_violations"] == "fail"


def test_enforcement_rejects_bad_mode(tmp_path):
    res = enforcement.set_enforcement(str(tmp_path), "banana")
    assert res["ok"] is False
