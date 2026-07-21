"""Shared test fixtures. All tests use an isolated BUSTER_HOME temp dir and
never require internet or a running model."""

from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point Buster at a throwaway home and reset all cached singletons."""
    home = tmp_path / "busterhome"
    monkeypatch.setenv("BUSTER_HOME", str(home))

    # Reset lru_cache singletons that captured paths/config from a prior test.
    import buster.config.paths as paths_mod

    paths_mod.get_paths.cache_clear()

    for mod_name, fn in [
        ("buster.database.db", "get_database"),
        ("buster.cache.manager", "get_cache"),
        ("buster.memory.service", "get_memory"),
        ("buster.reports.store", "get_report_store"),
        ("buster.research.manager", "get_research_manager"),
        ("buster.agent.tasks", "get_task_store"),
        ("buster.permissions.service", "get_permissions"),
        ("buster.actions.service", "get_actions"),
        ("buster.personality.service", "get_personality"),
        ("buster.prompts.service", "get_prompts"),
        ("buster.scheduler.alerts", "get_alerts"),
        ("buster.discovery.registry", "get_discovery"),
        ("buster.skills.registry", "get_skill_registry"),
        ("buster.tools.registry", "get_registry"),
    ]:
        mod = importlib.import_module(mod_name)
        getattr(mod, fn).cache_clear()

    yield home
