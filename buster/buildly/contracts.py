"""Local contract storage (P2.2 Phase 2).

Approving an inferred statement or feature turns it into a repository *contract*
stored as Git-trackable YAML under ``.buildly/contracts/``. This is legitimately
Buster-owned local continuity — the reconciliation ENGINE is bb-agent-manager's,
but the durable local record of what a human approved lives with the repo.

Guarantees (from the spec):
  * Inferred info is NEVER silently converted to approved truth — approval is an
    explicit action that records who/when.
  * Approved contracts are stored locally and survive restart.
  * Files are human-readable and reviewable in a PR.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

from buster.buildly.protocol import StatementStatus

_CONTRACTS_DIR = ".buildly/contracts"


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class ContractRecord(BaseModel):
    """A locally-approved contract derived from an inferred statement/feature."""

    id: str
    kind: str                       # feature | statement | product
    text: str
    status: StatementStatus = StatementStatus.APPROVED
    source_statement_id: str = ""
    product_id: str = ""
    approved_by: str = ""
    approved_at: str = ""
    edited: bool = False            # True if the human changed the proposed text
    labs_synced: bool = False
    labs_id: str = ""               # id in Labs once synced


class ContractStore:
    """Reads/writes .buildly/contracts/<id>.yaml for one repo."""

    def __init__(self, repo_path: str) -> None:
        self.repo = Path(repo_path).expanduser()
        self.dir = self.repo / _CONTRACTS_DIR

    def _path(self, contract_id: str) -> Path:
        return self.dir / f"{contract_id}.yaml"

    def save(self, record: ContractRecord) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(record.id)
        path.write_text(yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False))
        return path

    def get(self, contract_id: str) -> ContractRecord | None:
        path = self._path(contract_id)
        if not path.exists():
            return None
        return ContractRecord.model_validate(yaml.safe_load(path.read_text()))

    def list(self) -> list[ContractRecord]:
        if not self.dir.exists():
            return []
        out = []
        for f in sorted(self.dir.glob("*.yaml")):
            try:
                out.append(ContractRecord.model_validate(yaml.safe_load(f.read_text())))
            except Exception:  # noqa: BLE001
                continue
        return out

    # -- approval actions ----------------------------------------------------

    def approve(
        self, *, contract_id: str, kind: str, text: str, source_statement_id: str = "",
        product_id: str = "", approved_by: str = "user", edited: bool = False,
    ) -> ContractRecord:
        """Approve a statement/feature into a durable local contract."""
        rec = ContractRecord(
            id=contract_id, kind=kind, text=text, status=StatementStatus.APPROVED,
            source_statement_id=source_statement_id, product_id=product_id,
            approved_by=approved_by, approved_at=_now(), edited=edited,
        )
        self.save(rec)
        return rec

    def set_status(self, contract_id: str, status: StatementStatus,
                   by: str = "user") -> ContractRecord | None:
        """Reject / deprecate / keep-unresolved an existing record."""
        rec = self.get(contract_id)
        if rec is None:
            return None
        rec.status = status
        rec.approved_by = by
        rec.approved_at = _now()
        self.save(rec)
        return rec

    def mark_synced(self, contract_id: str, labs_id: str) -> None:
        rec = self.get(contract_id)
        if rec:
            rec.labs_synced = True
            rec.labs_id = labs_id
            self.save(rec)

    def pending_sync(self) -> list[ContractRecord]:
        """Approved contracts not yet synced to Labs."""
        return [c for c in self.list()
                if c.status == StatementStatus.APPROVED and not c.labs_synced]
