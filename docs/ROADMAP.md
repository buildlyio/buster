# Roadmap

## Phase 1 — Foundation (this release)

A working local-first assistant: install + service, CLI + web sharing one Core,
hardware/model detection, local-first Ollama routing (device → LAN), SQLite +
Markdown memory with FTS5, three-layer purgeable cache, tools + skills, web
research → Markdown reports, system + network diagnostics, permission-controlled
action plans with verification, deterministic alerts, LCDP + node/service
discovery, agent-runtime detection (Hermes/OpenClaw), Buildly Workspace
onboarding + mock adapters, prompt library, and a configurable personality.

## Explicitly deferred (interfaces exist, behavior does not)

- Multi-agent orchestration
- Autonomous Buster-to-Buster delegation
- Graph databases; mandatory vector databases
- Full voice assistant; email/calendar; messaging gateways
- Browser/computer automation; unrestricted shell
- Automatic skill installation; self-modifying code
- Community prompt sharing
- Production Labs mutation; production CollabHub matching
- Automatic remote AI fallback without user permission
- Kubernetes; required Docker deployment

## Phase 2 — Depth (planned)

> Detailed design: [PHASE2.md](PHASE2.md) — runtime task routing, Buildly MCP
> (bb-agent-manager), developer tooling (bb-code, tokenjam), and hosted model
> providers, all behind the existing gated-remote consent model.


- Remote/commercial provider implementations behind the existing
  `ModelProvider` protocol, gated by policy + explicit consent.
- Semantic index over `document_chunks` (SQLite vector search) behind the
  reserved interface.
- Real MCP-backed Buildly adapters (local + hosted).
- Read-only cross-node capability queries → scoped delegation.
- Streaming token deltas end-to-end in both clients.

## Phase 3 — Ecosystem (exploratory)

- Signed, sandboxed skill/tool-pack installation.
- Cross-node workload delegation with per-scope trust.
- Richer network/topology views and historical monitoring.
- Optional voice and additional channels.
