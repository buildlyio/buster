"""Runtime task-routing service.

Resolves a task-capable adapter for a runtime id, enforces the safety gate,
submits a bounded task, persists the run, normalizes events into Buster's bus,
and audits everything.

Safety gate (all must hold to submit to a REAL external runtime):
  * config.runtimes.allow_task_submission is True, AND
  * the runtime's stored trust is not "detected"/"ignored" (explicit opt-in), AND
  * a risk-level-2 permission has been approved for this submission.

The mock adapter path is always allowed (no external execution happens).
A run's output is DATA ONLY — it is never parsed into Buster tool calls/actions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from buster.config import load_config
from buster.database import get_database
from buster.events import Event, EventType, get_event_bus
from buster.permissions import RiskLevel, audit, get_permissions
from buster.runtimes.base import RunStatus, RuntimeRun, RuntimeTask
from buster.runtimes.cli_adapter import CliRuntimeAdapter
from buster.runtimes.mock_task import MockTaskAdapter


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class RuntimeSubmissionError(RuntimeError):
    pass


class RuntimeService:
    # Known CLI executables per runtime type (extended in Phase 2.3 for bb-code).
    _CLI = {
        "hermes": ("hermes", ["run", "{prompt}"]),
        "openclaw": ("openclaw", ["run", "{prompt}"]),
    }

    def _row(self, runtime_id: str) -> dict | None:
        r = get_database().query_one("SELECT * FROM runtimes WHERE id = ?", (runtime_id,))
        return dict(r) if r else None

    def _adapter(self, runtime_id: str):
        """Return a task-capable adapter, preferring a real CLI, else the mock.

        CLI config comes from the runtime's manifest (executable/argv_template,
        e.g. bb-code) if present, else the built-in _CLI map (hermes/openclaw).
        """
        import json as _json

        row = self._row(runtime_id)
        rtype = (row or {}).get("runtime_type", "")
        name = (row or {}).get("name", runtime_id)

        exe = argv = None
        # 1. manifest-defined CLI (bb-code and future manifest runtimes)
        manifest = (row or {}).get("manifest")
        if manifest:
            try:
                m = _json.loads(manifest)
                if m.get("executable") and m.get("argv_template"):
                    exe, argv = m["executable"], m["argv_template"]
            except Exception:  # noqa: BLE001
                pass
        # 2. built-in per-type map
        if exe is None and rtype in self._CLI:
            exe, argv = self._CLI[rtype]

        if exe is not None:
            cli = CliRuntimeAdapter(id=runtime_id, name=name, executable=exe, argv_template=argv)
            if cli.available():
                return cli
        # Fall back to a clearly-labelled mock (no external execution).
        return MockTaskAdapter(runtime_id, name)

    def is_real(self, runtime_id: str) -> bool:
        return not isinstance(self._adapter(runtime_id), MockTaskAdapter)

    async def request_submission(self, runtime_id: str, task: RuntimeTask):
        """Create a risk-2 permission request for submitting to a REAL runtime.

        Mock submissions don't need approval. Returns the permission (or None if
        no approval is required).
        """
        if not self.is_real(runtime_id):
            return None
        row = self._row(runtime_id)
        return await get_permissions().request(
            RiskLevel.SYSTEM_CHANGING,
            f"Submit a task to external runtime '{(row or {}).get('name', runtime_id)}'",
        )

    def _gate(self, runtime_id: str) -> None:
        if not self.is_real(runtime_id):
            return  # mock path is always allowed
        cfg = load_config()
        if not cfg.runtimes.allow_task_submission:
            raise RuntimeSubmissionError(
                "Task submission to external runtimes is disabled "
                "(set runtimes.allow_task_submission = true)."
            )
        row = self._row(runtime_id)
        trust = (row or {}).get("trust", "detected")
        if trust in ("detected", "ignored", ""):
            raise RuntimeSubmissionError(
                f"Runtime '{runtime_id}' is not trusted for task submission."
            )

    async def submit(self, runtime_id: str, task: RuntimeTask) -> RuntimeRun:
        self._gate(runtime_id)
        adapter = self._adapter(runtime_id)
        bus = get_event_bus()
        row = self._row(runtime_id)
        rtype = (row or {}).get("runtime_type", "")

        await bus.publish(Event(
            type=EventType.RUNTIME_TASK_STARTED,
            title=f"Task → {(row or {}).get('name', runtime_id)}",
            metadata={"runtime_id": runtime_id, "runtime_type": rtype,
                      "real": self.is_real(runtime_id)},
        ))

        run = await adapter.submit(task)
        self._persist(run, rtype, task.prompt)

        evt = {
            RunStatus.COMPLETED: EventType.RUNTIME_TASK_COMPLETED,
            RunStatus.FAILED: EventType.RUNTIME_TASK_FAILED,
            RunStatus.TIMEOUT: EventType.RUNTIME_TASK_FAILED,
            RunStatus.CANCELLED: EventType.RUNTIME_TASK_CANCELLED,
        }.get(run.status, EventType.RUNTIME_TASK_COMPLETED)
        await bus.publish(Event(
            type=evt,
            title=f"{(row or {}).get('name', runtime_id)}: {run.status.value}",
            metadata={
                "run_id": run.run_id, "runtime_id": runtime_id,
                "executing_runtime": run.executing_runtime, "model": run.model,
                "inference_location": run.inference_location,
                "external_data_shared": run.external_data_shared,
                "status": run.status.value,
            },
        ))
        audit(
            category="runtime", task_id=None,
            detail={"runtime_id": runtime_id, "run_id": run.run_id, "status": run.status.value,
                    "real": self.is_real(runtime_id)},
            result=run.status.value, model=run.model,
            inference_location=run.inference_location,
            external_data_shared=run.external_data_shared,
        )
        return run

    def _persist(self, run: RuntimeRun, rtype: str, prompt: str) -> None:
        now = _now()
        get_database().execute(
            "INSERT INTO runtime_runs (run_id, runtime_id, runtime_type, status, prompt, output, "
            "error, model, inference_location, external_data_shared, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, output=excluded.output, "
            "error=excluded.error, updated_at=excluded.updated_at",
            (run.run_id, run.runtime_id, rtype, run.status.value, prompt[:4000], run.output,
             run.error, run.model, run.inference_location, int(run.external_data_shared), now, now),
        )

    def get_run(self, run_id: str) -> dict | None:
        r = get_database().query_one("SELECT * FROM runtime_runs WHERE run_id = ?", (run_id,))
        return dict(r) if r else None

    def list_runs(self, runtime_id: str | None = None, limit: int = 50) -> list[dict]:
        db = get_database()
        if runtime_id:
            rows = db.query("SELECT * FROM runtime_runs WHERE runtime_id = ? "
                            "ORDER BY created_at DESC LIMIT ?", (runtime_id, limit))
        else:
            rows = db.query("SELECT * FROM runtime_runs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def get_runtime_service() -> RuntimeService:
    return RuntimeService()
