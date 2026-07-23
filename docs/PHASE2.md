# Buster Phase 2 — Design

Phase 2 extends the local-first foundation with **agent-runtime task routing**,
**Buildly MCP integration**, **developer tooling** (bb-code, tokenjam), and
**hosted model providers** — all behind Buster's existing consent and audit
model. Nothing here weakens the Phase 1 safety guarantees.

Status: design. Build order and scope agreed with the user:

1. Buster → Hermes / OpenClaw task routing  ← **DONE (v2 schema)**
2. bb-agent-manager (Buildly MCP) integration  ← DONE (Phase 1 + Phase 2)
3. Developer setup: bb-code + tokenjam  ← DONE
4. Hosted model providers (Claude / OpenAI)  ← DONE

Cross-cutting rule (agreed): **all cloud inference — hosted Claude/OpenAI,
Hugging Face, remote endpoints — reuses the single gated-remote path.** Default
policy stays local-first; any off-network call is opt-in, labelled in responses,
and written to the audit log. There is one consent model, not several.

---

## 1. Buster → Hermes / OpenClaw task routing (first)

Turns the Phase 1 runtime *detection* stubs into real, bounded task **submission**
and event normalization. This is the "delegation" work deferred in Phase 1 —
implemented conservatively.

### Principles (unchanged from Phase 1 security model)

- Task submission to a real external runtime is **off by default**
  (`runtimes.allow_task_submission = false`) and **per-runtime** opt-in.
- A delegated task returns **data only**. Its result can never cause Buster to
  auto-execute a system-changing action.
- External runtime permissions **never bypass** Buster's risk levels/approvals.
- Buster never imports another runtime's credentials, memory, history,
  schedules, or trusted nodes automatically.
- Prefer interfaces in order: official API → MCP → LCDP → supported CLI
  subprocess (strict argv + timeout) → read-only process discovery.

### Adapter contract (extends `buster/runtimes/base.py`)

```python
class RuntimeAdapter(Protocol):
    runtime_type: str
    async def detect(self) -> RuntimeInfo | None: ...
    async def health(self, info) -> RuntimeStatus: ...
    async def capabilities(self, info) -> list[str]: ...
    # NEW in Phase 2:
    async def submit(self, task: RuntimeTask) -> RuntimeRun: ...      # bounded
    async def stream(self, run_id: str) -> AsyncIterator[Event]: ...  # normalized
    async def cancel(self, run_id: str) -> None: ...
    async def logs(self, run_id: str, limit: int) -> list[str]: ...   # read-only
```

- `RuntimeTask`: `{prompt, timeout_s, max_tokens?, context_refs?}` — no shell,
  no file paths the runtime could abuse.
- `RuntimeRun`: `{run_id, runtime_id, status}`.
- Events from the external runtime are **normalized into Buster's event bus**
  (`runtime.task.started/…/completed`) so both clients show them with:
  coordinating runtime, executing runtime, model+provider, inference location,
  tools used (if known), data-sharing status, task status.

### Phase 1 → Phase 2 delta

- Real CLI-subprocess adapter with strict argv allow-list + timeout + output
  size cap (works for Hermes/OpenClaw when they expose a supported CLI).
- Real read-only detection where safe; mock adapters remain for tests/demos.
- `runtimes` table gains a `runs` companion (`runtime_runs`) for audit.
- New API: `POST /api/runtimes/{id}/submit`, `GET /api/runtimes/runs/{run}/events`
  (SSE), `POST /api/runtimes/runs/{run}/cancel`. Gated by config + a permission
  request (submitting to an external runtime is a risk-level-2 action).
- CLI: `buster runtimes`, `buster runtimes submit <id> "task"` (guarded).
- Web: the existing **Agents** section gains submit + live run view.

### Explicitly NOT in scope

- Autonomous multi-hop delegation (Buster→A→B).
- Any path where a delegated result auto-triggers a Buster action.

---

## 2. bb-agent-manager (Buildly MCP) integration

`bb-agent-manager` is a **model-agnostic MCP server** for Buildly Labs (issues,
products, features, milestones, project memory, devdocs, workflow/DoD checks).
It hosts no models and selects no model — that's the client's job, which is
exactly Buster's role.

### Integration

- Discover it via **LCDP** (`mcp_url`) or manual config, same trust flow as any
  service (discovered → trusted → workspace).
- A `BuildlyMcpAdapter` implements the existing `BuildlyAdapter` Protocol
  (`buster/buildly/adapter.py`), replacing the Phase 1 mock when
  `buildly.mode = "local_mcp"` / `"hosted_mcp"`.
- Expose Labs items (products/features/issues/opportunities) as **read** context
  and Buster tools; **writes** (create/close issue, DoD) are risk-level-2 and
  require approval — consistent with bb-agent-manager's "no auto-merge/close
  without human approval."
- Project memory from the MCP server augments Buster's context builder; it does
  not replace local Markdown memory.

### Config

```toml
[buildly]
workspace_enabled = true
mode = "local_mcp"          # local_mcp | hosted_mcp
mcp_url = "http://localhost:PORT/mcp"   # or stdio launcher
```

---

## 3. Developer setup: bb-code + tokenjam  ← DONE

A guided `buster dev setup` that detects and (with permission) installs two
independent, MIT/OSS developer tools. Buster **coexists** with them — never
replaces or wraps them silently — and always credits them.

### bb-code (Buildly-Marketplace/bb-code)

- Local-first CLI that scans a repo and generates an implementation plan with an
  Ollama model (local or trusted LAN) — the same inference tiers Buster uses.
- Buster registers it as a **CLI runtime** (§1 adapter) so `build .` plans can
  be launched and their events normalized, or simply detected + surfaced in the
  Agents/Dev section with a link to run it directly.
- Honors bb-code's own safety stance (no silent edits, no autonomous loops).
- With user opt-in, bb-code can point at a **hosted** model via §4 (gated).

### tokenjam (Metabuilder-Labs/tokenjam, MIT)

> TokenJam — token efficiency for AI agents. Reads your agent's telemetry, finds
> the waste, runs 100% local. © Metabuilder-Labs, MIT. Thanks to the TokenJam
> authors. https://github.com/Metabuilder-Labs/tokenjam

- Detect an existing tokenjam install (`tj`/`tokenjam` on PATH, or `pipx`).
- Offer to install via its supported path (`pipx install tokenjam`) **only with
  explicit approval** — Buster does not install packages silently.
- Surface `tj optimize` findings read-only in a Buster **Dev → Token usage**
  panel (parse its local output/telemetry; never send Buster data to it beyond
  what the user runs).
- Attribution + thanks shown in the UI and docs (per its MIT license).

### Attribution & licensing

- bb-code and bb-agent-manager: `licenseInfo: other` — treat as **integrate,
  don't vendor**. Buster calls/launches them; it does not copy their code.
- tokenjam: MIT — same (integrate, credit). If any snippet is ever vendored,
  include its MIT header. Default posture: no vendoring.

---

## 4. Hosted model providers (Claude / OpenAI)  ← DONE

Real Anthropic + OpenAI providers implementing the `ModelProvider` protocol,
plugged into the **gated-remote** path (not a new consent mechanism).

- Anthropic uses the latest Claude models; OpenAI uses its hosted models. Model
  IDs and defaults live in provider config, not hardcoded across the app.
- Enabled only when `inference.remote.enabled = true` **and**
  `policy = "no_restriction"` (or a future `hosted_ok` policy). Keys stored via
  OS credential store where available; redacted everywhere.
- Every hosted response sets `external_data_shared = true`, is labelled in the
  chat footer/event stream, and audited (model, provider, location).
- Used by general chat/research **and** by dev tools (bb-code codegen) when the
  user opts in.

### Router change

Extend `ModelRouter` tier 4/5 to select among configured hosted providers by
capability (e.g. coding → Claude/an OpenAI coding model) once local/LAN options
are exhausted or the user explicitly requests a hosted model.

---

## Testing (all phases)

- Mocked runtime adapters, MCP server, and hosted providers — **no network in
  the default test suite**.
- Safety tests that must stay green: remote/hosted never used under local-first;
  delegated results never auto-trigger actions; external writes require
  approval; secrets never logged.

## Deferred beyond Phase 2

Autonomous cross-runtime delegation, multi-agent orchestration, VS Code
extensions, auto-merge/auto-close, and any self-modifying behavior.
