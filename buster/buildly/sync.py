"""Offline-first synchronization journal (P2.2 Phase 2).

Local work is recorded as sync events under ``.buildly/sync/pending/`` as
Git-trackable JSON. When Labs (via bb-agent-manager) is reachable, ``push``
moves events pending → applied; on a conflict it records the event as a conflict
(never overwrites); on failure it moves it to failed for retry.

Non-negotiables honored:
  * Labs connectivity is NEVER required to record events.
  * Pending events survive restart (they're files).
  * Conflicts are never silently overwritten.
  * Safe to retry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from buster.buildly.protocol import SyncEvent, SyncState, SyncStatus

_SYNC = ".buildly/sync"


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class SyncJournal:
    def __init__(self, repo_path: str) -> None:
        self.repo = Path(repo_path).expanduser()
        self.root = self.repo / _SYNC
        self.pending = self.root / "pending"
        self.applied = self.root / "applied"
        self.failed = self.root / "failed"
        self.conflicts = self.root / "conflicts"

    def _dir(self, state: SyncState) -> Path:
        return {
            SyncState.PENDING: self.pending,
            SyncState.APPLIED: self.applied,
            SyncState.FAILED: self.failed,
            SyncState.CONFLICT: self.conflicts,
        }[state]

    # -- recording (always works, online or off) ----------------------------

    def record(self, kind: str, payload: dict) -> SyncEvent:
        evt = SyncEvent(id=f"evt_{uuid.uuid4().hex[:10]}", kind=kind,
                        state=SyncState.PENDING, created_at=_now(), payload=payload)
        self.pending.mkdir(parents=True, exist_ok=True)
        (self.pending / f"{evt.id}.json").write_text(evt.model_dump_json(indent=2))
        return evt

    def _load_dir(self, d: Path) -> list[SyncEvent]:
        if not d.exists():
            return []
        out = []
        for f in sorted(d.glob("*.json")):
            try:
                out.append(SyncEvent.model_validate_json(f.read_text()))
            except Exception:  # noqa: BLE001
                continue
        return out

    def pending_events(self) -> list[SyncEvent]:
        return self._load_dir(self.pending)

    def _move(self, evt: SyncEvent, to: SyncState) -> None:
        src = self.pending / f"{evt.id}.json"
        dst_dir = self._dir(to)
        dst_dir.mkdir(parents=True, exist_ok=True)
        evt.state = to
        (dst_dir / f"{evt.id}.json").write_text(evt.model_dump_json(indent=2))
        src.unlink(missing_ok=True)

    def status(self) -> SyncStatus:
        return SyncStatus(
            connected=False,  # filled in by the caller after an auth probe
            pending=len(self._load_dir(self.pending)),
            applied=len(self._load_dir(self.applied)),
            conflicts=len(self._load_dir(self.conflicts)),
            failed=len(self._load_dir(self.failed)),
        )

    # -- push (needs bb-agent-manager reachable) -----------------------------

    async def push(self, client, product_id: str = "") -> dict:
        """Push pending events through the MCP client. Returns a summary.

        Never raises on individual event failure — each event moves to
        applied / conflict / failed independently, so a bad event can't block
        the rest and the whole thing is safe to retry.
        """
        events = self.pending_events()
        applied = conflicts = failed = 0
        details: list[dict] = []
        for evt in events:
            try:
                outcome = await self._apply(client, evt, product_id)
            except Exception as exc:  # noqa: BLE001
                evt.error = str(exc)
                self._move(evt, SyncState.FAILED)
                failed += 1
                details.append({"id": evt.id, "state": "failed", "error": str(exc)})
                continue
            if outcome == "conflict":
                self._move(evt, SyncState.CONFLICT)
                conflicts += 1
                details.append({"id": evt.id, "state": "conflict"})
            elif outcome == "applied":
                self._move(evt, SyncState.APPLIED)
                applied += 1
                details.append({"id": evt.id, "state": "applied"})
            else:  # "failed" returned as data, not exception
                evt.error = str(outcome)
                self._move(evt, SyncState.FAILED)
                failed += 1
                details.append({"id": evt.id, "state": "failed", "error": str(outcome)})
        return {"applied": applied, "conflicts": conflicts, "failed": failed,
                "processed": len(events), "details": details}

    async def _apply(self, client, evt: SyncEvent, product_id: str) -> str:
        """Apply one event via the MCP client. Returns applied|conflict|<error>."""
        p = evt.payload
        if evt.kind == "contract.approved.feature":
            pid = p.get("product_id") or product_id
            if not pid:
                return "no product bound; cannot sync feature"
            res = await client.create_issue(pid, p.get("text", "Feature"),
                                             p.get("description", ""))
            return _classify(res)
        if evt.kind == "contract.approved.statement":
            pid = p.get("product_id") or product_id
            if not pid:
                return "no product bound; cannot sync statement"
            res = await client.create_issue(pid, p.get("text", "Statement"),
                                             p.get("description", ""))
            return _classify(res)
        if evt.kind == "issue.create":
            pid = p.get("product_id") or product_id
            res = await client.create_issue(pid, p["name"], p.get("description", ""))
            return _classify(res)
        # Unknown kind → leave it failed (safe; retryable after a fix).
        return f"unknown event kind: {evt.kind}"


def _classify(res: dict) -> str:
    """Map a bb-agent-manager tool result to applied|conflict|<error>."""
    if not isinstance(res, dict):
        return "applied"
    err = str(res.get("error", ""))
    if err.startswith("HTTP 409") or "conflict" in err.lower():
        return "conflict"
    if err:
        return err
    return "applied"
