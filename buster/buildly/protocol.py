"""Provisional typed client models for the Buildly AI-Native dev workflow.

IMPORTANT — these are PROVISIONAL. The canonical, versioned schemas belong in a
shared Buildly protocol package (not yet published). When that package exists,
replace these with generated/imported clients and delete this file. Keeping them
isolated here makes that swap mechanical.

Buster only *consumes* these shapes to render UX and collect approvals. The
contract/scan/sync/validation ENGINES live in bb-agent-manager, never here.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "provisional/0"


# -- enums --------------------------------------------------------------------

class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StatementStatus(str, Enum):
    OBSERVED = "observed"          # directly seen in the code
    INFERRED = "inferred"          # deduced, needs confirmation
    UNRESOLVED = "unresolved"      # couldn't determine
    CONTRADICTORY = "contradictory"  # conflicting evidence
    APPROVED = "approved"          # human-approved → becomes a contract
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class EnforcementMode(str, Enum):
    OBSERVE = "observe"
    RECORD = "record"
    GUIDE = "guide"
    ENFORCE_NEW = "enforce_new_work"
    FULL = "full_enforcement"


class SyncState(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    CONFLICT = "conflict"
    FAILED = "failed"


# -- repository / binding -----------------------------------------------------

class RepositoryContext(BaseModel):
    path: str
    is_git: bool = False
    default_branch: str = ""
    current_branch: str = ""
    framework: str = ""            # e.g. fastapi, django, react, node
    languages: list[str] = Field(default_factory=list)
    topology: str = "single"       # single | monorepo | multi-repo
    has_buildly_project: bool = False    # .buildly/project.yaml present
    has_local_memory: bool = False       # buildly_memory/ present
    has_pending_sync: bool = False       # .buildly/sync/pending present


class ProductBinding(BaseModel):
    bound: bool = False
    product_id: str = ""
    product_name: str = ""
    labs_url: str = ""
    mode: str = "local_only"       # local_only | connected


# -- contracts ----------------------------------------------------------------

class ProvenanceSource(BaseModel):
    file: str
    line_start: int | None = None
    line_end: int | None = None
    excerpt: str = ""


class InferredStatement(BaseModel):
    id: str
    text: str
    status: StatementStatus = StatementStatus.INFERRED
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    sources: list[ProvenanceSource] = Field(default_factory=list)
    related_routes: list[str] = Field(default_factory=list)
    related_models: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    related_screens: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)


class FeatureContract(BaseModel):
    id: str
    name: str
    description: str = ""
    status: StatementStatus = StatementStatus.INFERRED
    product_id: str = ""
    statements: list[str] = Field(default_factory=list)  # InferredStatement ids


class ProductContract(BaseModel):
    id: str
    name: str
    description: str = ""
    features: list[str] = Field(default_factory=list)    # FeatureContract ids


class IssueContract(BaseModel):
    id: str
    title: str
    source: str = "local"          # local | labs
    intent: str = ""
    scope_included: list[str] = Field(default_factory=list)
    scope_excluded: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    human_approvals_required: list[str] = Field(default_factory=list)
    likely_components: list[str] = Field(default_factory=list)


# -- adoption -----------------------------------------------------------------

class AdoptionInventory(BaseModel):
    frameworks: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    apps_packages: list[str] = Field(default_factory=list)
    api_routes: list[str] = Field(default_factory=list)
    models_schemas: list[str] = Field(default_factory=list)
    migrations: list[str] = Field(default_factory=list)
    frontend_routes: list[str] = Field(default_factory=list)
    api_clients: list[str] = Field(default_factory=list)
    auth_patterns: list[str] = Field(default_factory=list)
    background_jobs: list[str] = Field(default_factory=list)
    events_queues: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    existing_docs: list[str] = Field(default_factory=list)
    build_deploy: list[str] = Field(default_factory=list)


class AdoptionReport(BaseModel):
    repository: str
    generated_at: str = ""
    inventory: AdoptionInventory = Field(default_factory=AdoptionInventory)
    proposed_features: list[FeatureContract] = Field(default_factory=list)
    statements: list[InferredStatement] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    contradictory: list[str] = Field(default_factory=list)
    # Where the human-readable outputs were written.
    output_dirs: list[str] = Field(default_factory=list)
    engine: str = "mock"           # mock | bb-agent-manager


# -- work / agents / validation ----------------------------------------------

class ContextPackage(BaseModel):
    id: str
    issue_id: str
    summary: str = ""
    included_files: list[str] = Field(default_factory=list)
    excluded_note: str = ""        # e.g. "secrets and unrelated files excluded"
    token_estimate: int = 0
    engine: str = "mock"


class AgentRun(BaseModel):
    id: str
    issue_id: str
    agent: str = ""
    model: str = ""
    context_package_id: str = ""
    prompt: str = ""
    started_at: str = ""
    finished_at: str = ""
    outcome: str = "pending"       # pending | running | completed | failed


class ValidationResult(BaseModel):
    check: str
    passed: bool
    detail: str = ""


class ChangeManifest(BaseModel):
    id: str
    run_id: str = ""
    changed_files: list[str] = Field(default_factory=list)
    tests: list[ValidationResult] = Field(default_factory=list)
    contract_changes: list[str] = Field(default_factory=list)
    security_effects: list[str] = Field(default_factory=list)
    migration_effects: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class AcceptanceEvidence(BaseModel):
    issue_id: str
    criteria: str
    satisfied: bool
    evidence: str = ""


# -- sync ---------------------------------------------------------------------

class SyncEvent(BaseModel):
    id: str
    kind: str                      # contract.approved | issue.updated | ...
    state: SyncState = SyncState.PENDING
    created_at: str = ""
    payload: dict = Field(default_factory=dict)
    error: str = ""


class SyncConflict(BaseModel):
    id: str
    field: str
    local_value: str = ""
    labs_value: str = ""
    resolution: str = ""           # keep_local | keep_labs | merge | defer


class SyncStatus(BaseModel):
    connected: bool = False
    last_success: str = ""
    pending: int = 0
    applied: int = 0
    conflicts: int = 0
    failed: int = 0


class HumanApproval(BaseModel):
    id: str
    subject: str
    approved: bool = False
    approved_by: str = ""
    approved_at: str = ""
