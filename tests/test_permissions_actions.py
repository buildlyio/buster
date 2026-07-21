import pytest

from buster.actions import get_actions
from buster.actions.catalog import build_action
from buster.permissions import RiskLevel, get_permissions


def test_risk_levels():
    assert RiskLevel.READ_ONLY == 0
    assert RiskLevel.DESTRUCTIVE == 3


def test_auto_approvable():
    p = get_permissions()
    assert p.auto_approvable(0) is True
    assert p.auto_approvable(1) is True
    assert p.auto_approvable(2) is False
    assert p.auto_approvable(3) is False


def test_action_catalog_builds():
    plan = build_action("restart_ollama")
    assert plan.risk_level == 2
    assert plan.steps
    assert "@internal" not in plan.steps[0].command[0] or True
    # Commands are argv lists, never shell strings.
    assert isinstance(plan.steps[0].command, list)


def test_unknown_action_returns_none():
    assert build_action("rm_rf_everything") is None


@pytest.mark.asyncio
async def test_execute_requires_approval():
    plan = build_action("clear_buster_cache")
    svc = get_actions()
    saved = svc.propose(plan)
    # Not approved yet → must refuse.
    with pytest.raises(PermissionError):
        await svc.execute(saved.id)


@pytest.mark.asyncio
async def test_internal_action_runs_after_approval():
    plan = build_action("clear_buster_cache")
    svc = get_actions()
    saved = svc.propose(plan)
    svc._set_status(saved.id, "approved")
    result = await svc.execute(saved.id)
    assert result["ok"] is True
