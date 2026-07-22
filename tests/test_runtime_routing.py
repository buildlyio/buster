"""Phase 2.1 — Buster→runtime task routing.

Safety-critical tests: the submission gate, data-only results, and the mock path.
No real external runtime is invoked.
"""

import pytest

from buster.config import load_config, save_config
from buster.runtimes import RuntimeSubmissionError, RuntimeTask, get_runtime_service
from buster.runtimes.mock_task import MockTaskAdapter


@pytest.fixture
def svc(monkeypatch):
    s = get_runtime_service()
    # Force the mock adapter for a synthetic runtime id.
    monkeypatch.setattr(s, "_adapter", lambda rid: MockTaskAdapter(rid, "MockRT"))
    return s


@pytest.mark.asyncio
async def test_mock_submission_is_data_only(svc):
    run = await svc.submit("runtime.mock", RuntimeTask(prompt="hello"))
    assert run.status.value == "completed"
    assert "mock:MockRT" in run.output
    assert run.external_data_shared is False
    # The run is persisted for audit.
    assert any(r["run_id"] == run.run_id for r in svc.list_runs())


@pytest.mark.asyncio
async def test_mock_path_needs_no_permission(svc):
    # Mock adapter is not "real", so is_real is False and no approval is needed.
    assert svc.is_real("runtime.mock") is False
    run = await svc.submit("runtime.mock", RuntimeTask(prompt="x"))
    assert run.status.value == "completed"


@pytest.mark.asyncio
async def test_real_runtime_blocked_when_submission_disabled(monkeypatch):
    """A real runtime must be blocked unless submission is enabled AND trusted."""
    s = get_runtime_service()

    # Make the runtime look real.
    monkeypatch.setattr(s, "is_real", lambda rid: True)
    monkeypatch.setattr(s, "_row", lambda rid: {"name": "Hermes", "trust": "trusted",
                                                 "runtime_type": "hermes"})

    cfg = load_config()
    cfg.runtimes.allow_task_submission = False
    save_config(cfg)

    with pytest.raises(RuntimeSubmissionError):
        await s.submit("runtime.hermes", RuntimeTask(prompt="do a thing"))


@pytest.mark.asyncio
async def test_real_runtime_blocked_when_untrusted(monkeypatch):
    s = get_runtime_service()
    monkeypatch.setattr(s, "is_real", lambda rid: True)
    monkeypatch.setattr(s, "_row", lambda rid: {"name": "Hermes", "trust": "detected",
                                                 "runtime_type": "hermes"})
    cfg = load_config()
    cfg.runtimes.allow_task_submission = True  # enabled...
    save_config(cfg)
    # ...but trust is only "detected" → still blocked.
    with pytest.raises(RuntimeSubmissionError):
        await s.submit("runtime.hermes", RuntimeTask(prompt="do a thing"))


def test_runtime_task_is_bounded():
    """RuntimeTask carries no shell/paths — just prompt + limits."""
    t = RuntimeTask(prompt="hi")
    fields = set(t.model_dump().keys())
    assert fields == {"prompt", "timeout_s", "max_output_bytes", "context"}


@pytest.mark.asyncio
async def test_cli_adapter_reports_missing_executable():
    """CLI adapter fails gracefully (data-only error) when the exe is absent."""
    from buster.runtimes.cli_adapter import CliRuntimeAdapter

    a = CliRuntimeAdapter(id="runtime.none", name="None",
                          executable="definitely-not-a-real-binary-xyz",
                          argv_template=["run", "{prompt}"])
    assert a.available() is False
    run = await a.submit(RuntimeTask(prompt="x"))
    assert run.status.value == "failed"
    assert "not found" in run.error
