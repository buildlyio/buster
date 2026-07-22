"""Mock BuildlyDevelopmentService.

Simulates the engines that will live in bb-agent-manager (adoption scan, context
package, change manifest, sync) so Buster's UX and tests work before they exist.
Every result is labelled engine="mock". Repository inspection and binding use the
real local helpers (they're legitimately Buster-owned and read-only).

Safety honored by the mock:
  * The adoption scan writes ONLY under .buildly/adoption/ and devdocs/generated/
    — never touches existing application files.
  * Inferred statements are produced with status=INFERRED (never approved).
  * No Labs connectivity required.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

from buster.buildly.devservice import inspect_repository_local
from buster.buildly.protocol import (
    AdoptionInventory,
    AdoptionReport,
    ChangeManifest,
    ConfidenceLevel,
    ContextPackage,
    FeatureContract,
    InferredStatement,
    ProductBinding,
    ProvenanceSource,
    RepositoryContext,
    StatementStatus,
    SyncConflict,
    SyncStatus,
    ValidationResult,
)

_ADOPTION_DIR = ".buildly/adoption"
_DEVDOCS_DIR = "devdocs/generated"
_SYNC_PENDING = ".buildly/sync/pending"


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _sid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class MockBuildlyDevelopmentService:
    engine = "mock"

    # -- repository / binding (real local helpers) ---------------------------

    async def inspect_repository(self, path: str) -> RepositoryContext:
        return inspect_repository_local(path)

    async def get_binding(self, path: str) -> ProductBinding:
        proj = Path(path) / ".buildly" / "project.yaml"
        if proj.exists():
            try:
                data = yaml.safe_load(proj.read_text()) or {}
                return ProductBinding(
                    bound=True, mode="connected",
                    product_id=str(data.get("product_id", "")),
                    product_name=str(data.get("product_name", "")),
                    labs_url=str(data.get("labs_url", "")),
                )
            except Exception:  # noqa: BLE001
                pass
        return ProductBinding(bound=False, mode="local_only")

    async def connect_product(self, path: str, product_id: str) -> ProductBinding:
        # Write the binding locally (mock; real impl would confirm with Labs).
        proj_dir = Path(path) / ".buildly"
        proj_dir.mkdir(parents=True, exist_ok=True)
        binding = {"product_id": product_id, "product_name": f"Product {product_id}",
                   "labs_url": "", "schema": "provisional/0"}
        (proj_dir / "project.yaml").write_text(yaml.safe_dump(binding))
        return ProductBinding(bound=True, mode="connected", product_id=product_id,
                              product_name=binding["product_name"])

    # -- adoption scan (mock engine; observation-only, safe writes) ----------

    async def scan_repository(self, path: str) -> AdoptionReport:
        repo = inspect_repository_local(path)
        inv = self._scan_inventory(path, repo)
        statements = self._infer_statements(inv)
        features = self._propose_features(statements)

        report = AdoptionReport(
            repository=path,
            generated_at=_now(),
            inventory=inv,
            proposed_features=features,
            statements=statements,
            unresolved=[s.id for s in statements if s.status == StatementStatus.UNRESOLVED],
            contradictory=[s.id for s in statements if s.status == StatementStatus.CONTRADICTORY],
            engine=self.engine,
        )
        # Write human-readable, Git-trackable outputs — ONLY in the safe dirs.
        out_dirs = self._write_outputs(path, report)
        report.output_dirs = out_dirs
        return report

    def _scan_inventory(self, path: str, repo: RepositoryContext) -> AdoptionInventory:
        p = Path(path)
        inv = AdoptionInventory(frameworks=[repo.framework] if repo.framework else [],
                                languages=repo.languages)
        # Read-only glob-based inventory (bounded; never opens huge trees fully).
        py = list(p.rglob("*.py"))[:2000]
        for f in py:
            rel = str(f.relative_to(p))
            if "test" in rel.lower():
                inv.tests.append(rel)
            if "migration" in rel.lower():
                inv.migrations.append(rel)
            if rel.endswith(("models.py", "schema.py", "schemas.py")):
                inv.models_schemas.append(rel)
            if any(k in rel.lower() for k in ("route", "api", "views", "endpoint")):
                inv.api_routes.append(rel)
        for name in ("README.md", "docs", "openapi.json", "openapi.yaml"):
            if (p / name).exists():
                inv.existing_docs.append(name)
        for name in ("Dockerfile", "docker-compose.yml", ".github/workflows",
                     "pyproject.toml", "requirements.txt", "package.json"):
            if (p / name).exists():
                inv.build_deploy.append(name)
        # Cap list sizes for readability.
        for field in ("tests", "migrations", "models_schemas", "api_routes"):
            setattr(inv, field, getattr(inv, field)[:50])
        return inv

    def _infer_statements(self, inv: AdoptionInventory) -> list[InferredStatement]:
        out: list[InferredStatement] = []
        if inv.api_routes:
            out.append(InferredStatement(
                id=_sid("stmt"),
                text=f"The application exposes an HTTP API ({len(inv.api_routes)} route file(s)).",
                status=StatementStatus.OBSERVED, confidence=ConfidenceLevel.HIGH,
                sources=[ProvenanceSource(file=inv.api_routes[0])],
                related_routes=inv.api_routes[:5],
            ))
        if inv.models_schemas:
            out.append(InferredStatement(
                id=_sid("stmt"),
                text="The application defines persistent data models.",
                status=StatementStatus.OBSERVED, confidence=ConfidenceLevel.HIGH,
                sources=[ProvenanceSource(file=inv.models_schemas[0])],
                related_models=inv.models_schemas[:5],
            ))
        if inv.tests:
            out.append(InferredStatement(
                id=_sid("stmt"),
                text=f"The application has an automated test suite ({len(inv.tests)} files).",
                status=StatementStatus.OBSERVED, confidence=ConfidenceLevel.HIGH,
                related_tests=inv.tests[:5],
            ))
        # An example inferred (not observed) statement needing confirmation.
        if inv.api_routes and inv.models_schemas:
            out.append(InferredStatement(
                id=_sid("stmt"),
                text="This appears to be a CRUD-style backend service.",
                status=StatementStatus.INFERRED, confidence=ConfidenceLevel.MEDIUM,
                sources=[ProvenanceSource(file=inv.api_routes[0]),
                         ProvenanceSource(file=inv.models_schemas[0])],
            ))
        return out

    def _propose_features(self, statements: list[InferredStatement]) -> list[FeatureContract]:
        if not statements:
            return []
        return [FeatureContract(
            id=_sid("feat"),
            name="Core API",
            description="Proposed feature boundary covering the service's HTTP API and models.",
            status=StatementStatus.INFERRED,
            statements=[s.id for s in statements
                        if s.related_routes or s.related_models],
        )]

    def _write_outputs(self, path: str, report: AdoptionReport) -> list[str]:
        p = Path(path)
        adoption = p / _ADOPTION_DIR
        devdocs = p / _DEVDOCS_DIR
        adoption.mkdir(parents=True, exist_ok=True)
        devdocs.mkdir(parents=True, exist_ok=True)

        (adoption / "inventory.json").write_text(
            json.dumps(report.inventory.model_dump(), indent=2))
        (adoption / "statements.json").write_text(
            json.dumps([s.model_dump() for s in report.statements], indent=2))
        # A readable overview doc.
        lines = [f"# Adoption report — {Path(path).name}", "",
                 f"_Generated {report.generated_at} · engine: {report.engine} "
                 "(observation-only; no application files were modified)_", "",
                 "## Proposed features", ""]
        for f in report.proposed_features:
            lines.append(f"- **{f.name}** — {f.description} _(status: {f.status.value})_")
        lines += ["", "## Statements", ""]
        for s in report.statements:
            src = f" (source: {s.sources[0].file})" if s.sources else ""
            lines.append(f"- [{s.status.value} · {s.confidence.value}] {s.text}{src}")
        (devdocs / "adoption-overview.md").write_text("\n".join(lines))
        return [str(adoption), str(devdocs)]

    async def get_adoption_report(self, path: str) -> AdoptionReport | None:
        f = Path(path) / _ADOPTION_DIR / "statements.json"
        inv = Path(path) / _ADOPTION_DIR / "inventory.json"
        if not (f.exists() and inv.exists()):
            return None
        try:
            statements = [InferredStatement.model_validate(s)
                          for s in json.loads(f.read_text())]
            inventory = AdoptionInventory.model_validate(json.loads(inv.read_text()))
        except Exception:  # noqa: BLE001
            return None
        return AdoptionReport(repository=path, inventory=inventory, statements=statements,
                              engine=self.engine, output_dirs=[str(Path(path) / _ADOPTION_DIR)])

    # -- docs / diagrams (mock) ----------------------------------------------

    async def generate_documentation(self, path: str) -> list[str]:
        devdocs = Path(path) / _DEVDOCS_DIR
        devdocs.mkdir(parents=True, exist_ok=True)
        f = devdocs / "product-overview.md"
        f.write_text(f"# Product overview (generated)\n\n_engine: {self.engine}_\n\n"
                     "Generated documentation will be produced by bb-agent-manager.\n")
        return [str(f)]

    async def generate_diagrams(self, path: str) -> list[str]:
        devdocs = Path(path) / _DEVDOCS_DIR
        devdocs.mkdir(parents=True, exist_ok=True)
        f = devdocs / "architecture.mmd"
        f.write_text("flowchart TD\n  Client --> API\n  API --> Models\n  Models --> DB[(Database)]\n")
        return [str(f)]

    # -- work / context / manifest / sync (mock) -----------------------------

    async def create_context_package(self, path: str, issue_id: str) -> ContextPackage:
        # Mock: include a couple of relevant files; explicitly note exclusions.
        files = [str(f.relative_to(path)) for f in list(Path(path).rglob("*.py"))[:5]]
        return ContextPackage(
            id=_sid("ctx"), issue_id=issue_id,
            summary=f"Bounded context for {issue_id} (mock).",
            included_files=files,
            excluded_note="Secrets, env files, and unrelated modules excluded.",
            token_estimate=1200, engine=self.engine,
        )

    async def create_change_manifest(self, path: str, run_id: str) -> ChangeManifest:
        return ChangeManifest(
            id=_sid("chg"), run_id=run_id,
            changed_files=[], tests=[ValidationResult(check="unit", passed=True, detail="mock")],
            unresolved_questions=["Confirm the feature boundary with the product owner."],
        )

    async def get_sync_status(self, path: str) -> SyncStatus:
        pending_dir = Path(path) / _SYNC_PENDING
        pending = len(list(pending_dir.glob("*.json"))) if pending_dir.exists() else 0
        return SyncStatus(connected=False, pending=pending)

    async def list_conflicts(self, path: str) -> list[SyncConflict]:
        return []


def get_dev_service() -> MockBuildlyDevelopmentService:
    """Return the active dev service. Phase 1 uses the mock; a real MCP-backed
    implementation plugs in here later (selected by config.buildly.mode)."""
    return MockBuildlyDevelopmentService()
