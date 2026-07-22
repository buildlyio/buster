"""Uninstall removes the service artifacts, venv, and CLI shim (idempotently)."""

import os
from pathlib import Path

import buster.cli.service as svc


def _make_install(home: Path) -> dict:
    (home / "Library/LaunchAgents").mkdir(parents=True)
    (home / ".buster/venv/bin").mkdir(parents=True)
    (home / ".local/bin").mkdir(parents=True)
    plist = home / "Library/LaunchAgents/io.buildly.buster.plist"
    plist.write_text("<plist/>")
    shim = home / ".local/bin/buster"
    shim.write_text("#!/bin/sh\n")
    os.chmod(shim, 0o755)
    return {"plist": plist, "shim": shim, "venv": home / ".buster/venv"}


def test_remove_service_and_program(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    art = _make_install(home)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    # Avoid touching launchctl/systemctl in the test environment.
    monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: None)

    assert art["plist"].exists() and art["shim"].exists() and art["venv"].exists()
    svc.remove_service()
    svc.remove_program()
    assert not art["plist"].exists()
    assert not art["shim"].exists()
    assert not art["venv"].exists()


def test_uninstall_is_idempotent(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: None)
    # Nothing installed → must not raise.
    svc.remove_service()
    svc.remove_program()


def test_keep_program_flag(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    art = _make_install(home)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: None)
    svc.remove_service()
    # remove_program not called → venv + shim remain.
    assert art["venv"].exists()
    assert art["shim"].exists()
