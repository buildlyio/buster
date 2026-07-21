"""Catalog of safe, pre-defined action plans.

Only actions in this catalog can be proposed/executed. This is the boundary
that prevents arbitrary command execution: models pick a catalog key, they do
not author commands. Platform-specific variants are resolved at build time.
"""

from __future__ import annotations

import sys

from buster.actions.model import ActionPlan, ActionStep, Verification


def _restart_ollama() -> ActionPlan:
    if sys.platform == "darwin":
        # macOS: Ollama typically runs as a login app; use brew services if present.
        steps = [ActionStep(command=["brew", "services", "restart", "ollama"],
                            description="Restart Ollama via Homebrew services")]
        rollback = [ActionStep(command=["brew", "services", "stop", "ollama"])]
    else:
        steps = [ActionStep(command=["systemctl", "--user", "restart", "ollama"],
                            description="Restart the Ollama user service")]
        rollback = [ActionStep(command=["systemctl", "--user", "stop", "ollama"])]
    return ActionPlan(
        title="Restart Ollama service",
        risk_level=2,
        preconditions=["Ollama is installed", "Ollama is currently stopped or unhealthy"],
        steps=steps,
        verification=[Verification(request="http://localhost:11434/api/tags", expect_status=200)],
        rollback=rollback,
    )


def _clear_buster_cache() -> ActionPlan:
    # Executed via an internal handler (see service), not a shell command.
    return ActionPlan(
        title="Clear Buster temporary cache",
        risk_level=1,
        preconditions=["Buster owns the cache directory"],
        steps=[ActionStep(command=["@internal", "cache.clear_temp"],
                          description="Clear temp + web cache namespaces")],
        verification=[],
        rollback=[],
    )


def _restart_buster() -> ActionPlan:
    return ActionPlan(
        title="Restart Buster service",
        risk_level=1,
        preconditions=["Buster service manager available"],
        steps=[ActionStep(command=["@internal", "service.restart"],
                          description="Restart the Buster background service")],
        verification=[],
        rollback=[],
    )


# key -> factory (evaluated lazily so platform is resolved at call time)
ACTION_CATALOG: dict[str, callable] = {
    "restart_ollama": _restart_ollama,
    "clear_buster_cache": _clear_buster_cache,
    "restart_buster": _restart_buster,
}


def build_action(key: str) -> ActionPlan | None:
    factory = ACTION_CATALOG.get(key)
    return factory() if factory else None
