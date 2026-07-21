"""Action service: propose → approve → execute → verify, with full audit.

Execution runs argv lists without a shell. Internal ``@internal`` steps route
to trusted Python handlers (never subprocess). Every action is audited.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from functools import lru_cache

import httpx

from buster.actions.model import ActionPlan
from buster.database import get_database
from buster.events import Event, EventType, get_event_bus
from buster.permissions import audit


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class ActionService:
    def propose(self, plan: ActionPlan, task_id: str | None = None) -> ActionPlan:
        if not plan.id:
            plan.id = f"action_{uuid.uuid4().hex[:10]}"
        db = get_database()
        now = _now()
        db.execute(
            "INSERT INTO actions (id, task_id, title, risk_level, plan, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)",
            (plan.id, task_id, plan.title, plan.risk_level, plan.model_dump_json(), now, now),
        )
        audit(category="action", detail={"title": plan.title, "state": "proposed"},
              task_id=task_id, risk_level=plan.risk_level, result="proposed")
        return plan

    def get(self, action_id: str) -> ActionPlan | None:
        row = get_database().query_one("SELECT plan FROM actions WHERE id = ?", (action_id,))
        return ActionPlan.model_validate_json(row["plan"]) if row else None

    def _set_status(self, action_id: str, status: str, result: dict | None = None) -> None:
        get_database().execute(
            "UPDATE actions SET status = ?, updated_at = ?, result = ? WHERE id = ?",
            (status, _now(), json.dumps(result or {}), action_id),
        )

    async def execute(self, action_id: str) -> dict:
        """Execute an approved action and verify it. Returns a result dict."""
        plan = self.get(action_id)
        if plan is None:
            raise KeyError(action_id)
        row = get_database().query_one("SELECT status, task_id FROM actions WHERE id = ?", (action_id,))
        if row["status"] not in ("approved",):
            raise PermissionError(f"Action {action_id} is not approved (status: {row['status']})")
        task_id = row["task_id"]

        await get_event_bus().publish(
            Event(type=EventType.ACTION_STARTED, task_id=task_id, title=plan.title,
                  metadata={"action_id": action_id, "risk_level": plan.risk_level})
        )
        self._set_status(action_id, "running")

        step_results = []
        for step in plan.steps:
            res = await self._run_step(step.command)
            step_results.append(res)
            if not res["ok"]:
                self._set_status(action_id, "failed", {"steps": step_results})
                audit(category="action", detail={"title": plan.title, "step": step.command},
                      task_id=task_id, risk_level=plan.risk_level, approved=True, result="failed")
                return {"ok": False, "steps": step_results}

        verified = await self._verify(plan)
        status = "verified" if verified else "failed"
        self._set_status(action_id, status, {"steps": step_results, "verified": verified})
        await get_event_bus().publish(
            Event(type=EventType.ACTION_VERIFIED, task_id=task_id, title=plan.title,
                  metadata={"action_id": action_id, "verified": verified})
        )
        audit(category="action", detail={"title": plan.title}, task_id=task_id,
              risk_level=plan.risk_level, approved=True, result=status)
        return {"ok": verified, "steps": step_results, "verified": verified}

    async def _run_step(self, command: list[str]) -> dict:
        if command and command[0] == "@internal":
            return await self._run_internal(command[1:])
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
            return {
                "command": command,
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": out.decode(errors="replace")[-2000:],
                "stderr": err.decode(errors="replace")[-2000:],
            }
        except FileNotFoundError as exc:
            return {"command": command, "ok": False, "error": f"command not found: {exc}"}
        except TimeoutError:
            return {"command": command, "ok": False, "error": "timeout"}

    async def _run_internal(self, args: list[str]) -> dict:
        handler = args[0] if args else ""
        if handler == "cache.clear_temp":
            from buster.cache import get_cache
            from buster.cache.manager import NS_WEB

            cache = get_cache()
            n = cache.clear_temp() + cache.clear_namespace(NS_WEB)
            return {"command": ["@internal", handler], "ok": True, "cleared": n}
        if handler == "service.restart":
            # Signalled to the service manager elsewhere; here we just ack.
            return {"command": ["@internal", handler], "ok": True, "note": "restart requested"}
        return {"command": ["@internal", handler], "ok": False, "error": "unknown internal handler"}

    async def _verify(self, plan: ActionPlan) -> bool:
        if not plan.verification:
            return True
        for v in plan.verification:
            if v.request:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as c:
                        r = await c.get(v.request)
                    if r.status_code != v.expect_status:
                        return False
                except Exception:  # noqa: BLE001
                    return False
            elif v.command:
                res = await self._run_step(v.command)
                if not res["ok"]:
                    return False
        return True

    def list(self, limit: int = 50) -> list[dict]:
        rows = get_database().query("SELECT * FROM actions ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def get_actions() -> ActionService:
    return ActionService()
