"""Core REST API routes + SSE stream.

Both clients (CLI, web) use these endpoints. Nothing here exposes model
chain-of-thought; events describe activity only.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from buster import __version__
from buster.actions import get_actions
from buster.actions.catalog import build_action
from buster.agent import get_task_store
from buster.agent.loop import Agent
from buster.buildly import get_buildly_adapter
from buster.config import load_config
from buster.diagnostics import run_doctor
from buster.diagnostics.network import run_network_check
from buster.diagnostics.system import run_system_check
from buster.discovery import build_self_manifest, get_discovery
from buster.events import get_event_bus
from buster.memory import get_memory
from buster.models.capability import detect_capabilities
from buster.models.router import ModelRouter
from buster.permissions import get_permissions
from buster.permissions.audit import recent as recent_audit
from buster.personality import get_personality
from buster.prompts import get_prompts
from buster.prompts.service import PromptRecord
from buster.reports import get_report_store
from buster.research import get_research_manager
from buster.scheduler import get_alerts
from buster.tools import get_registry

router = APIRouter()


# -- health / status ----------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/status")
async def status() -> dict:
    config = load_config()
    router_ = ModelRouter(config)
    prof = detect_capabilities()
    models = await router_.available_models()
    nodes = get_discovery().list_nodes()
    trusted = [n for n in nodes if n["trust"] != "discovered" and n["trust"] != "ignored"]
    return {
        "version": __version__,
        "capability_profile": prof.model_dump(),
        "models": [m.model_dump() for m in models],
        "inference_policy": config.inference.policy,
        "trusted_nodes": len(trusted),
        "personality": get_personality().current_profile(),
    }


@router.get("/doctor")
async def doctor() -> dict:
    report = await run_doctor()
    return report.model_dump()


# -- events (SSE) --------------------------------------------------------------

@router.get("/events")
async def events(task_id: str | None = None):
    bus = get_event_bus()

    async def gen():
        # Replay recent history first.
        for e in bus.recent(task_id=task_id, limit=50):
            yield e.sse()
        async with bus.subscribe() as q:
            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=15.0)
                    if task_id and e.task_id != task_id:
                        continue
                    yield e.sse()
                except TimeoutError:
                    yield ": keep-alive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/events/recent")
async def events_recent(task_id: str | None = None, limit: int = 100) -> dict:
    return {"events": [e.model_dump() for e in get_event_bus().recent(task_id, limit)]}


# -- chat / ask ----------------------------------------------------------------

class AskRequest(BaseModel):
    prompt: str
    conversation_id: str | None = None


@router.post("/ask")
async def ask(req: AskRequest) -> dict:
    agent = Agent()
    result = await agent.run(req.prompt, conversation_id=req.conversation_id)
    return result.model_dump()


@router.get("/conversations")
async def conversations() -> dict:
    return {"conversations": get_task_store().list_conversations()}


@router.post("/conversations")
async def new_conversation() -> dict:
    cid = get_task_store().create_conversation()
    return {"id": cid}


@router.get("/conversations/{cid}/messages")
async def conversation_messages(cid: str) -> dict:
    return {"messages": [m.model_dump() for m in get_task_store().messages(cid)]}


# -- tasks ---------------------------------------------------------------------

@router.get("/tasks")
async def tasks() -> dict:
    return {"tasks": [t.model_dump() for t in get_task_store().list()]}


# -- research ------------------------------------------------------------------

class ResearchRequest(BaseModel):
    question: str


@router.post("/research")
async def start_research(req: ResearchRequest) -> dict:
    from buster.research.workflow import run_quick_research

    result = await run_quick_research(req.question)
    return result


@router.get("/research")
async def list_research() -> dict:
    return {"projects": [p.model_dump() for p in get_research_manager().list_projects()]}


# -- reports -------------------------------------------------------------------

@router.get("/reports")
async def reports() -> dict:
    return {"reports": get_report_store().list()}


@router.get("/reports/{report_id}")
async def report_show(report_id: str) -> dict:
    md = get_report_store().get_markdown(report_id)
    meta = get_report_store().get_meta(report_id)
    if md is None:
        raise HTTPException(404, "Report not found")
    return {"meta": meta, "markdown": md}


# -- diagnostics ---------------------------------------------------------------

@router.get("/system/check")
async def system_check() -> dict:
    return {"checks": [c.model_dump() for c in run_system_check()]}


@router.get("/network/check")
async def network_check() -> dict:
    return {"checks": [c.model_dump() for c in await run_network_check()]}


# -- alerts --------------------------------------------------------------------

@router.get("/alerts")
async def alerts() -> dict:
    return {"alerts": get_alerts().list()}


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str) -> dict:
    get_alerts().acknowledge(alert_id)
    return {"ok": True}


# -- permissions ---------------------------------------------------------------

@router.get("/permissions/pending")
async def pending_permissions() -> dict:
    return {"pending": [p.model_dump() for p in get_permissions().pending()]}


class DecideRequest(BaseModel):
    approved: bool


@router.post("/permissions/{permission_id}/decide")
async def decide_permission(permission_id: str, req: DecideRequest) -> dict:
    await get_permissions().decide(permission_id, req.approved)
    return {"ok": True}


# -- actions -------------------------------------------------------------------

class ProposeActionRequest(BaseModel):
    catalog_key: str
    task_id: str | None = None


@router.post("/actions/propose")
async def propose_action(req: ProposeActionRequest) -> dict:
    plan = build_action(req.catalog_key)
    if plan is None:
        raise HTTPException(400, "Unknown action")
    saved = get_actions().propose(plan, task_id=req.task_id)
    perm = await get_permissions().request(plan.risk_level, plan.title, task_id=req.task_id,
                                           action_id=saved.id)
    return {"action": saved.model_dump(), "preview": saved.preview(),
            "permission_id": perm.id, "risk_level": plan.risk_level}


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str) -> dict:
    get_actions()._set_status(action_id, "approved")
    result = await get_actions().execute(action_id)
    return result


@router.get("/actions")
async def list_actions() -> dict:
    return {"actions": get_actions().list()}


# -- memory --------------------------------------------------------------------

@router.get("/memory/search")
async def memory_search(q: str, limit: int = 8) -> dict:
    return {"hits": [h.model_dump() for h in get_memory().search(q, limit)]}


# -- tools / skills ------------------------------------------------------------

@router.get("/tools")
async def tools() -> dict:
    return {"tools": [t.model_dump() for t in get_registry().all()]}


@router.get("/skills")
async def skills() -> dict:
    from buster.skills import get_skill_registry

    return {"skills": [s.model_dump() for s in get_skill_registry().all()]}


# -- discovery / nodes / services ----------------------------------------------

@router.get("/discovery/manifest")
async def self_manifest() -> dict:
    return build_self_manifest().model_dump(by_alias=True)


@router.get("/nodes")
async def nodes() -> dict:
    return {"nodes": get_discovery().list_nodes()}


@router.get("/services")
async def services() -> dict:
    return {"services": get_discovery().list_services()}


class TrustRequest(BaseModel):
    trust: str


@router.post("/services/{service_id}/trust")
async def trust_service(service_id: str, req: TrustRequest) -> dict:
    get_discovery().set_service_trust(service_id, req.trust)
    return {"ok": True}


@router.post("/nodes/{node_id}/trust")
async def trust_node(node_id: str, req: TrustRequest) -> dict:
    get_discovery().set_node_trust(node_id, req.trust)
    return {"ok": True}


@router.get("/network/graph")
async def network_graph() -> dict:
    """Deterministic node/edge graph. The LLM never invents devices."""
    disco = get_discovery()
    self_m = build_self_manifest()
    graph_nodes = [{"id": self_m.id, "label": self_m.name, "type": "buster", "self": True}]
    edges = []
    for n in disco.list_nodes():
        graph_nodes.append({"id": n["id"], "label": n["name"], "type": "buster",
                            "trust": n["trust"]})
        edges.append({"from": self_m.id, "to": n["id"]})
    for s in disco.list_services():
        graph_nodes.append({"id": s["id"], "label": s["name"], "type": "service",
                            "trust": s["trust"]})
        edges.append({"from": self_m.id, "to": s["id"]})
    return {"nodes": graph_nodes, "edges": edges}


# -- runtimes ------------------------------------------------------------------

@router.get("/runtimes")
async def runtimes() -> dict:
    from buster.runtimes import detect_runtimes

    return {"runtimes": [r.model_dump() for r in await detect_runtimes()]}


class RuntimeTrustRequest(BaseModel):
    trust: str


@router.post("/runtimes/{runtime_id}/trust")
async def trust_runtime(runtime_id: str, req: RuntimeTrustRequest) -> dict:
    from buster.database import get_database

    get_database().execute("UPDATE runtimes SET trust = ? WHERE id = ?", (req.trust, runtime_id))
    return {"ok": True}


class RuntimeSubmitRequest(BaseModel):
    prompt: str
    timeout_s: int = 120
    # For a REAL external runtime, an approved permission id is required.
    permission_id: str | None = None


@router.post("/runtimes/{runtime_id}/submit")
async def submit_runtime_task(runtime_id: str, req: RuntimeSubmitRequest) -> dict:
    from buster.runtimes import RuntimeSubmissionError, RuntimeTask, get_runtime_service

    svc = get_runtime_service()
    task = RuntimeTask(prompt=req.prompt, timeout_s=req.timeout_s)

    # Real runtimes require an approved risk-2 permission.
    if svc.is_real(runtime_id):
        if not req.permission_id:
            raise HTTPException(428, "This runtime requires an approved permission "
                                     "(POST /runtimes/{id}/request-submission first).")
        perm = get_permissions().get(req.permission_id)
        if not perm or perm.status != "approved":
            raise HTTPException(403, "Submission permission is not approved.")

    try:
        run = await svc.submit(runtime_id, task)
    except RuntimeSubmissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return run.model_dump()


@router.post("/runtimes/{runtime_id}/request-submission")
async def request_runtime_submission(runtime_id: str, req: RuntimeSubmitRequest) -> dict:
    """Create the risk-2 permission needed to submit to a REAL runtime."""
    from buster.runtimes import RuntimeTask, get_runtime_service

    svc = get_runtime_service()
    if not svc.is_real(runtime_id):
        return {"permission_required": False}
    perm = await svc.request_submission(runtime_id, RuntimeTask(prompt=req.prompt))
    return {"permission_required": True, "permission_id": perm.id if perm else None}


@router.get("/runtimes/runs")
async def runtime_runs(runtime_id: str | None = None) -> dict:
    from buster.runtimes import get_runtime_service

    return {"runs": get_runtime_service().list_runs(runtime_id)}


@router.get("/runtimes/runs/{run_id}")
async def runtime_run(run_id: str) -> dict:
    from buster.runtimes import get_runtime_service

    run = get_runtime_service().get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


# -- prompts -------------------------------------------------------------------

@router.get("/prompts")
async def prompts() -> dict:
    return {"prompts": [p.model_dump() for p in get_prompts().list()]}


@router.post("/prompts")
async def save_prompt(record: PromptRecord) -> dict:
    saved = get_prompts().save(record)
    return saved.model_dump()


@router.get("/prompts/search")
async def search_prompts(q: str) -> dict:
    return {"prompts": [p.model_dump() for p in get_prompts().search(q)]}


@router.get("/prompts/{prompt_id}")
async def show_prompt(prompt_id: str) -> dict:
    rec = get_prompts().get(prompt_id)
    if not rec:
        raise HTTPException(404, "Prompt not found")
    return rec.model_dump()


# -- buildly workspace ---------------------------------------------------------

@router.get("/buildly/products")
async def buildly_products() -> dict:
    adapter = get_buildly_adapter()
    return {"products": [p.model_dump() for p in await adapter.products()]}


@router.get("/buildly/opportunities")
async def buildly_opportunities() -> dict:
    adapter = get_buildly_adapter()
    return {"opportunities": [o.model_dump() for o in await adapter.opportunities()]}


# -- Buildly dev workflow (P2.2 Phase 1) --------------------------------------
# Buster is the coordinator: it inspects the repo locally, shows binding/offline
# status, launches the (mock) adoption scan, and renders reports. Engines belong
# to bb-agent-manager. Labs is never required for local operation.

class RepoRequest(BaseModel):
    path: str


@router.post("/dev/inspect")
async def dev_inspect(req: RepoRequest) -> dict:
    from buster.buildly.devservice_mock import get_dev_service

    svc = get_dev_service()
    ctx = await svc.inspect_repository(req.path)
    binding = await svc.get_binding(req.path)
    sync = await svc.get_sync_status(req.path)
    return {"repository": ctx.model_dump(), "binding": binding.model_dump(),
            "sync": sync.model_dump(), "engine": svc.engine}


class ConnectRequest(BaseModel):
    path: str
    product_id: str


@router.post("/dev/connect")
async def dev_connect(req: ConnectRequest) -> dict:
    from buster.buildly.devservice_mock import get_dev_service

    binding = await get_dev_service().connect_product(req.path, req.product_id)
    return binding.model_dump()


@router.post("/dev/scan")
async def dev_scan(req: RepoRequest) -> dict:
    """Run the observation-only adoption scan. Never modifies application files."""
    from buster.buildly.devservice_mock import get_dev_service
    from buster.events import Event, EventType, get_event_bus

    svc = get_dev_service()
    await get_event_bus().publish(Event(type=EventType.RESEARCH_STARTED,
                                        title=f"Adoption scan: {req.path}",
                                        metadata={"engine": svc.engine}))
    report = await svc.scan_repository(req.path)
    return report.model_dump()


@router.get("/dev/adoption")
async def dev_adoption(path: str) -> dict:
    from buster.buildly.devservice_mock import get_dev_service

    report = await get_dev_service().get_adoption_report(path)
    if report is None:
        raise HTTPException(404, "No adoption report yet — run a scan first.")
    return report.model_dump()


@router.post("/dev/docs")
async def dev_docs(req: RepoRequest) -> dict:
    from buster.buildly.devservice_mock import get_dev_service

    svc = get_dev_service()
    docs = await svc.generate_documentation(req.path)
    diagrams = await svc.generate_diagrams(req.path)
    return {"docs": docs, "diagrams": diagrams, "engine": svc.engine}


# -- personality / config ------------------------------------------------------

@router.get("/personality")
async def personality() -> dict:
    svc = get_personality()
    return {"profile": svc.current_profile(), "profiles": svc.profiles(),
            "history": svc.history()}


class ProfileRequest(BaseModel):
    profile: str


@router.post("/personality")
async def set_personality(req: ProfileRequest) -> dict:
    get_personality().set_profile(req.profile)
    return {"ok": True, "profile": req.profile}


@router.get("/config")
async def get_config() -> dict:
    return load_config().model_dump()


@router.get("/audit")
async def audit_log(limit: int = 100) -> dict:
    return {"audit": recent_audit(limit)}
