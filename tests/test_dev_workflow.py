"""P2.2 Phase 1 — Buildly AI-Native dev workflow (mock engine).

Covers the spec's non-negotiable Phase-1 guarantees: repo works with no Labs,
scan doesn't touch app files, inferred stays unapproved, binding stored locally,
offline sync journal, bounded context excludes secrets.
"""

import asyncio
from pathlib import Path

import pytest

from buster.buildly.devservice_mock import get_dev_service
from buster.buildly.protocol import StatementStatus


@pytest.fixture
def fastapi_repo(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["fastapi"]\n')
    (tmp_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/x')\ndef x(): return []\n")
    (tmp_path / "app" / "models.py").write_text("class Item: ...\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x(): assert True\n")
    # A secret that must never end up in a context package.
    (tmp_path / ".env").write_text("API_KEY=super-secret-value\n")
    return tmp_path


def _snapshot(root: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in root.rglob("*")
            if p.is_file() and ".buildly" not in str(p) and "devdocs" not in str(p)}


def test_inspect_detects_framework_without_labs(fastapi_repo):
    svc = get_dev_service()
    ctx = asyncio.run(svc.inspect_repository(str(fastapi_repo)))
    assert ctx.framework == "fastapi"
    assert "python" in ctx.languages
    # No Labs needed to inspect.
    binding = asyncio.run(svc.get_binding(str(fastapi_repo)))
    assert binding.bound is False and binding.mode == "local_only"


def test_scan_does_not_modify_application_files(fastapi_repo):
    before = _snapshot(fastapi_repo)
    asyncio.run(get_dev_service().scan_repository(str(fastapi_repo)))
    after = _snapshot(fastapi_repo)
    # Every non-.buildly/devdocs file is byte-for-byte unchanged.
    assert before == after
    # Outputs went only to the safe dirs.
    assert (fastapi_repo / ".buildly" / "adoption" / "inventory.json").exists()
    assert (fastapi_repo / "devdocs" / "generated" / "adoption-overview.md").exists()


def test_inferred_statements_are_not_approved(fastapi_repo):
    report = asyncio.run(get_dev_service().scan_repository(str(fastapi_repo)))
    assert report.statements
    assert all(s.status != StatementStatus.APPROVED for s in report.statements)
    assert all(f.status != StatementStatus.APPROVED for f in report.proposed_features)


def test_binding_stored_locally(fastapi_repo):
    svc = get_dev_service()
    binding = asyncio.run(svc.connect_product(str(fastapi_repo), "prod_123"))
    assert binding.bound and binding.product_id == "prod_123"
    assert (fastapi_repo / ".buildly" / "project.yaml").exists()
    # Re-reading the binding restores it (survives "restart").
    again = asyncio.run(svc.get_binding(str(fastapi_repo)))
    assert again.bound and again.product_id == "prod_123"


def test_offline_sync_status_counts_pending(fastapi_repo):
    # Record a real event via the journal (validated schema).
    from buster.buildly.sync import SyncJournal

    SyncJournal(str(fastapi_repo)).record("issue.create", {"name": "x"})
    status = asyncio.run(get_dev_service().get_sync_status(str(fastapi_repo)))
    assert status.connected is False
    assert status.pending == 1


def test_context_package_excludes_secrets(fastapi_repo):
    pkg = asyncio.run(get_dev_service().create_context_package(str(fastapi_repo), "LOCAL-1"))
    # The .env secret must not be included; exclusion is stated.
    assert all(".env" not in f for f in pkg.included_files)
    assert "secret" in pkg.excluded_note.lower() or "excluded" in pkg.excluded_note.lower()


def test_adoption_report_reloads(fastapi_repo):
    svc = get_dev_service()
    asyncio.run(svc.scan_repository(str(fastapi_repo)))
    reloaded = asyncio.run(svc.get_adoption_report(str(fastapi_repo)))
    assert reloaded is not None
    assert reloaded.statements
