"""Dev workflow Phase 3 — work → context → agent run → review.

Verifies: context packages exclude secrets/skip-dirs, runs + manifests persist,
real-runtime runs require approval, and review never auto-merges.
"""

import asyncio

import pytest

from buster.buildly.devservice_mock import get_dev_service
from buster.buildly.protocol import IssueContract
from buster.buildly.work import WorkStore, issue_from_labs


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "api.py").write_text("from fastapi import FastAPI\napp=FastAPI()\n")
    (tmp_path / "app" / "models.py").write_text("class Item: ...\n")
    (tmp_path / ".env").write_text("SECRET_KEY=xyz\n")
    (tmp_path / "deploy.pem").write_text("KEY\n")
    (tmp_path / "credentials.json").write_text("{}\n")
    return tmp_path


def test_context_package_excludes_secrets(repo):
    store = WorkStore(str(repo))
    issue = IssueContract(id="I-1", title="add items api", source="local")
    pkg = store.build_context_package(issue)
    assert pkg.included_files
    assert not any(".env" in f or ".pem" in f or "credentials" in f for f in pkg.included_files)
    assert "secret" in pkg.excluded_note.lower()


def test_context_package_persists_and_reloads(repo):
    store = WorkStore(str(repo))
    pkg = store.build_context_package(IssueContract(id="I-2", title="x", source="local"))
    assert (repo / ".buildly" / "work" / "context" / f"{pkg.id}.json").exists()
    assert store.get_context_package(pkg.id) is not None


def test_issue_from_labs_maps_fields():
    ic = issue_from_labs({"id": "LABS-7", "name": "Fix bug", "description": "boom"})
    assert ic.source == "labs" and ic.id == "LABS-7" and ic.title == "Fix bug"


@pytest.mark.asyncio
async def test_start_work_builds_context(repo):
    svc = get_dev_service()
    res = await svc.start_work(str(repo), {"id": "L-1", "title": "endpoint", "source": "local"})
    assert res["context_package"]["issue_id"] == "L-1"
    assert res["context_package"]["included_files"]


@pytest.mark.asyncio
async def test_run_agent_mock_records_run(repo):
    svc = get_dev_service()
    res = await svc.start_work(str(repo), {"id": "L-1", "title": "x", "source": "local"})
    out = await svc.run_agent(str(repo), res["context_package"]["id"], "runtime.mock-abc")
    assert out["run"]["outcome"] == "completed"
    # persisted
    runs = await svc.list_runs(str(repo))
    assert any(r["id"] == out["run"]["id"] for r in runs)


@pytest.mark.asyncio
async def test_run_agent_real_runtime_requires_permission(repo, monkeypatch):
    svc = get_dev_service()
    res = await svc.start_work(str(repo), {"id": "L-1", "title": "x", "source": "local"})

    # Make the runtime look real, no permission supplied.
    from buster.runtimes.service import get_runtime_service

    monkeypatch.setattr(get_runtime_service(), "is_real", lambda rid: True)
    out = await svc.run_agent(str(repo), res["context_package"]["id"], "runtime.hermes")
    assert out.get("permission_required") is True
    assert "error" in out


@pytest.mark.asyncio
async def test_review_never_auto_merges(repo):
    svc = get_dev_service()
    res = await svc.review_changes(str(repo), "run_x")
    assert "never auto-merge" in res["note"].lower()
    assert (repo / ".buildly" / "work" / "manifests").exists()
