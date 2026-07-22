"""P2.2 Phase 2 — approval → local contracts → offline sync journal.

Covers the spec's non-negotiables: approve records a contract locally, inferred
stays unapproved until an explicit action, pending events survive, failed/offline
pushes never lose events, conflicts are recorded not overwritten.
"""

import asyncio

import pytest

from buster.buildly.contracts import ContractStore
from buster.buildly.devservice_mock import get_dev_service
from buster.buildly.protocol import StatementStatus, SyncState
from buster.buildly.sync import SyncJournal


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["fastapi"]\n')
    (tmp_path / "app" / "api.py").write_text("from fastapi import FastAPI\napp=FastAPI()\n")
    (tmp_path / "app" / "models.py").write_text("class Item: ...\n")
    return tmp_path


def test_approve_writes_local_contract(repo):
    svc = get_dev_service()
    report = asyncio.run(svc.scan_repository(str(repo)))
    sid = report.statements[0].id
    res = asyncio.run(svc.approve_statement(str(repo), sid))
    cid = res["contract"]["id"]
    # Contract persisted as Git-trackable YAML.
    assert (repo / ".buildly" / "contracts" / f"{cid}.yaml").exists()
    store = ContractStore(str(repo))
    rec = store.get(cid)
    assert rec.status == StatementStatus.APPROVED
    assert rec.approved_at  # who/when recorded


def test_edit_and_approve_marks_edited(repo):
    svc = get_dev_service()
    report = asyncio.run(svc.scan_repository(str(repo)))
    sid = report.statements[0].id
    res = asyncio.run(svc.approve_statement(str(repo), sid, text="A better description"))
    assert res["contract"]["edited"] is True
    assert res["contract"]["text"] == "A better description"


def test_reject_is_local_only_no_sync_event(repo):
    svc = get_dev_service()
    report = asyncio.run(svc.scan_repository(str(repo)))
    sid = report.statements[0].id
    asyncio.run(svc.set_statement_status(str(repo), sid, "rejected"))
    # No pending sync event created by a rejection.
    assert SyncJournal(str(repo)).status().pending == 0
    rec = ContractStore(str(repo)).get(f"contract_{sid}")
    assert rec.status == StatementStatus.REJECTED


def test_approve_queues_pending_event(repo):
    svc = get_dev_service()
    report = asyncio.run(svc.scan_repository(str(repo)))
    asyncio.run(svc.approve_statement(str(repo), report.statements[0].id))
    assert SyncJournal(str(repo)).status().pending == 1


def test_pending_events_survive_reload(repo):
    j = SyncJournal(str(repo))
    j.record("issue.create", {"name": "X"})
    # A fresh journal instance (like a restart) still sees it.
    assert SyncJournal(str(repo)).status().pending == 1


@pytest.mark.asyncio
async def test_offline_push_preserves_events(repo, monkeypatch):
    svc = get_dev_service()
    report = await svc.scan_repository(str(repo))
    await svc.approve_statement(str(repo), report.statements[0].id)

    # Force "no MCP configured" → offline.
    from buster.buildly import mcp_client

    monkeypatch.setattr(mcp_client, "_resolve_target",
                        lambda: mcp_client.McpTarget(mcp_client.McpTransport.NONE, ""))
    res = await svc.sync_push(str(repo))
    assert res["pushed"] is False
    assert SyncJournal(str(repo)).status().pending == 1  # nothing lost


@pytest.mark.asyncio
async def test_push_records_conflict_without_overwrite(repo):
    j = SyncJournal(str(repo))
    j.record("issue.create", {"name": "conflicting", "product_id": "p1"})

    class FakeClient:
        async def create_issue(self, product_id, name, description=""):
            return {"error": "HTTP 409 conflict"}

    result = await j.push(FakeClient(), product_id="p1")
    assert result["conflicts"] == 1 and result["applied"] == 0
    status = j.status()
    assert status.conflicts == 1 and status.pending == 0  # moved, not deleted


@pytest.mark.asyncio
async def test_push_applies_on_success(repo):
    j = SyncJournal(str(repo))
    j.record("issue.create", {"name": "ok", "product_id": "p1"})

    class FakeClient:
        async def create_issue(self, product_id, name, description=""):
            return {"status": "ok", "data": {"id": "new"}}

    result = await j.push(FakeClient(), product_id="p1")
    assert result["applied"] == 1
    assert j.status().applied == 1 and j.status().pending == 0


@pytest.mark.asyncio
async def test_push_failure_moves_to_failed_not_lost(repo):
    j = SyncJournal(str(repo))
    j.record("issue.create", {"name": "boom", "product_id": "p1"})

    class FakeClient:
        async def create_issue(self, *a, **k):
            raise RuntimeError("network died mid-call")

    result = await j.push(FakeClient(), product_id="p1")
    assert result["failed"] == 1
    assert j.status().failed == 1 and j.status().pending == 0  # retryable, not lost
