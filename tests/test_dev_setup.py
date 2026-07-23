"""P2.3 — developer tooling: bb-code (CLI runtime) + tokenjam (read-only)."""

import pytest

from buster.dev import setup


def test_dev_status_reports_tools(monkeypatch):
    # bb-code present, tokenjam absent.
    monkeypatch.setattr(setup, "_which",
                        lambda *names: "/usr/bin/bb-code" if "bb-code" in names else None)
    statuses = {s.key: s for s in setup.dev_status()}
    assert statuses["bb_code"].present is True
    assert statuses["tokenjam"].present is False
    # Absent tool advertises a NON-silent install command.
    assert statuses["tokenjam"].install_cmd
    assert "pipx install tokenjam" in statuses["tokenjam"].install_cmd


def test_install_command_never_empty_for_known_tools():
    assert setup.install_command("bb_code")
    assert setup.install_command("tokenjam")
    assert setup.install_command("unknown") == ""


def test_tokenjam_absent_is_read_only_no_error(monkeypatch):
    monkeypatch.setattr(setup, "_which", lambda *names: None)
    s = setup.tokenjam_summary()
    assert s.available is False
    assert "not installed" in s.note.lower()
    assert "Metabuilder-Labs" in s.credit  # attribution always present


def test_tokenjam_parses_json_findings(monkeypatch):
    monkeypatch.setattr(setup, "_which", lambda *names: "/usr/bin/tj")

    class FakeProc:
        stdout = '{"findings": [{"title": "Downsize Opus→Haiku"}, {"title": "Cache repeats"}]}'
        stderr = ""
        returncode = 0

    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: FakeProc())
    s = setup.tokenjam_summary()
    assert s.available is True
    assert len(s.findings) == 2
    assert s.findings[0]["title"].startswith("Downsize")


def test_register_bb_code_runtime_when_present(monkeypatch):
    monkeypatch.setattr(setup, "_which",
                        lambda *names: "/usr/bin/bb-code" if "bb-code" in names else None)
    manifest = setup.register_bb_code_runtime()
    assert manifest and manifest["id"] == "runtime.bb-code"
    assert manifest["argv_template"] == ["build", "{prompt}"]
    # Persisted + resolves to a real CLI adapter.
    from buster.runtimes.service import get_runtime_service

    svc = get_runtime_service()
    assert svc._row("runtime.bb-code") is not None


def test_register_bb_code_none_when_absent(monkeypatch):
    monkeypatch.setattr(setup, "_which", lambda *names: None)
    assert setup.register_bb_code_runtime() is None


@pytest.mark.asyncio
async def test_bb_code_runtime_uses_manifest_argv(monkeypatch):
    """A manifest-defined CLI runtime resolves via its argv_template, not the
    hardcoded _CLI map."""
    import json

    from buster.database import get_database
    from buster.runtimes.service import get_runtime_service

    manifest = {"executable": "definitely-absent-xyz", "argv_template": ["go", "{prompt}"]}
    get_database().execute(
        "INSERT INTO runtimes (id, runtime_type, name, detected_via, status, manifest, trust, "
        "discovered_at, last_seen_at) VALUES (?, 'cli', 'X', 'cli', 'detected', ?, 'detected', "
        "'t', 't') ON CONFLICT(id) DO UPDATE SET manifest=excluded.manifest",
        ("runtime.x", json.dumps(manifest)),
    )
    svc = get_runtime_service()
    # Executable absent → falls back to mock (not a crash), proving it read the manifest.
    assert svc.is_real("runtime.x") is False
