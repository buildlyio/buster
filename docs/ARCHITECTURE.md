# Buster Architecture

Buster is a lightweight, hardware-adaptive, local-first assistant for research,
reporting, machine diagnostics, network monitoring, and safe action. This
document describes the Phase 1 foundation.

## Design principles

1. **Local first.** Prefer models running on the current device. Remote
   inference is only used when necessary and permitted (see the model router).
2. **Hardware adaptive.** Detect the machine's capabilities and adapt. Raspberry
   Pi is the *minimum* tier, implemented as an adapter — not the core design.
3. **Lightweight at rest.** No mandatory Docker, Kubernetes, Redis, Postgres,
   Node.js on the target, or external vector/graph databases. Python + SQLite +
   Markdown + filesystem only.
4. **User control.** Buster distinguishes observation, interpretation,
   recommendation, proposed action, approved action, and verified result. It
   never silently changes the system, installs packages, or sends data remotely.

## Shared Core, two clients

Buster is **one assistant** exposed through two first-class clients (CLI and
local web). All agent, task, research, and permission logic lives in **Buster
Core**. Clients are thin: they call the Core API and subscribe to the Core event
stream.

```
Buster Core
├── Agent runtime        (bounded agent loop)
├── Context builder      (relevant context bundle, not whole files)
├── Model router         (local-first routing + policy)
├── Tool registry        (typed tools, permission levels)
├── Skill registry       (Markdown workflows)
├── Memory service       (SQLite FTS5 + Markdown)
├── Cache manager        (memory / SQLite index / filesystem objects)
├── Research manager     (workspaces, sources, reports)
├── Diagnostics          (system + network, read-only first)
├── Discovery            (LCDP, mDNS, nodes, runtimes)
├── Permissions          (risk levels 0-3, action plans)
├── Scheduler            (deterministic alerts, no LLM required)
└── Event stream         (SSE/WebSocket + terminal rendering)
      ├── CLI  (Typer + Rich)
      └── Web  (FastAPI + Jinja + HTMX, precompiled assets)
```

A conversation started in the CLI is visible in the web UI. A permission request
raised in the web UI is visible in the CLI. A report generated anywhere is stored
once and available everywhere.

## Process model

Buster runs as a **modular monolith** with background workers, managed as a
user-level service (`systemd --user` on Linux, `launchd` user agent on macOS).
The API server (FastAPI/Uvicorn) hosts the Core; the scheduler and job queue run
in-process. Jobs are backed by SQLite and an in-process asyncio queue — no Redis.

## Determinism without an LLM

Monitoring, discovery, threshold alerts, health checks, scheduling, caching, and
service management run **without** an LLM. The agent loop is only invoked for
natural-language tasks. `buster doctor`, `buster system check`, and the scheduler
work with no model loaded.

## Data & storage

- **SQLite** (WAL, single controlled writer) — structured store + FTS5 retrieval.
- **Markdown** — durable human-readable memory, reports, notes.
- **Filesystem** — reports, research sources, attachments, cache objects.
- **Bounded in-memory cache** — active context, tool defs, capability profile.

See [DATABASE.md](DATABASE.md) for the schema and migration approach.

## Security model

See [SECURITY.md](SECURITY.md). Summary: all tool/content from the web, logs,
files, MCP, and discovered services is treated as untrusted data, never as
instructions. Commands are constructed by trusted tool code, never emitted-and-run
from raw model text. The web server binds to localhost by default.

## Event stream

A structured internal event system (`buster/events`) drives both clients. Events
are typed Pydantic models, persisted to `task_events`, and streamed over SSE.
Events describe *what Buster is doing* (tool running, source read, model
selected, inference location, action needing approval, verified result) but never
raw model chain-of-thought.

## Module map

| Module | Responsibility |
|---|---|
| `config` | TOML config, validated defaults, paths |
| `database` | SQLite connection, migrations, controlled writer |
| `events` | Event models + in-process bus + SSE bridge |
| `api` | FastAPI app, routes, SSE endpoint |
| `cli` | Typer commands + Rich interactive mode |
| `web` | FastAPI-served Jinja/HTMX UI, precompiled assets |
| `agent` | Bounded agent loop, task classification |
| `models` | Provider protocol, Ollama provider, model router |
| `context` | Context builder (relevance-bounded bundles) |
| `memory` | Markdown memory + FTS5 index |
| `cache` | Three-layer cache + purge controls |
| `tools` | Tool registry, tool packs, decorator |
| `skills` | Skill registry (Markdown workflows) |
| `research` | Research workspaces, fetch/extract, reports |
| `reports` | Structured report model + Markdown generation |
| `diagnostics` | System + network checks (OS adapters) |
| `actions` | Structured action plans + verification |
| `permissions` | Risk levels, approval flow, audit |
| `discovery` | LCDP manifest, mDNS, service registry |
| `nodes` | Buster node discovery + trust |
| `runtimes` | Agent-runtime adapters (Hermes, OpenClaw, ...) |
| `scheduler` | Deterministic alerts + scheduled reports |
| `personality` | Personality model + profiles |
| `buildly` | Optional Buildly Workspace integration |

## Extension interfaces (built, not fully populated in Phase 1)

- `ModelProvider` protocol — add remote/commercial providers later.
- Tool `@tool` decorator + registry — drop-in tool packs.
- Markdown skill format — reusable workflows.
- LCDP manifest + adapters — discover any local capability.
- Runtime adapters — coexist with Hermes/OpenClaw/generic runtimes.
- Semantic-index interface — future SQLite vector search (stubbed).
