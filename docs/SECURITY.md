# Buster Security Model

Buster is local-first and treats the user as the authority. This document
describes the trust boundaries and controls in Phase 1.

## Trust boundary: everything from tools is untrusted data

Content from web pages, logs, files, MCP servers, and discovered services is
**data, not instructions**. Buster never lets such content directly trigger:

- shell commands
- package installation
- file deletion
- credential use
- permission changes
- tool installation
- external data transmission

Tool results carry an `untrusted` label when the pack declares
`untrusted_output=True` (e.g. `web.fetch`, `web.search`, `files.read`), and the
agent wraps tool output so the model sees it as quoted data.

## No arbitrary command execution

The model can *select* tools and *select* catalog actions, but it can never
author a shell string. Concretely:

- Tools are typed async functions. Arguments are validated against a Pydantic
  model before the tool runs (`ToolRegistry.invoke`).
- Actions are fixed `argv` lists built by trusted catalog code
  (`buster/actions/catalog.py`) and executed **without a shell**
  (`asyncio.create_subprocess_exec`, never `shell=True`).
- Internal actions route to a small allowlist of Python handlers.

## Risk levels & permission flow

| Level | Meaning | Handling |
|---|---|---|
| 0 | read-only | normally allowed |
| 1 | safe Buster-owned | may be pre-approved (restart Buster, clear cache) |
| 2 | system-changing | always requires confirmation (restart Ollama, …) |
| 3 | destructive | exact preview + explicit confirmation (delete, reboot) |

The agent auto-runs only level 0–1 tools; level ≥2 requires an explicit
approval surfaced as a `permission.requested` event in both clients. Actions
record `proposed → approved → running → verified/failed` with an audit entry at
each stage.

## Observation → action distinction

Buster distinguishes observation, interpretation, recommendation, proposed
action, approved action, and verified result. It never silently installs
packages, changes settings, connects services, sends data remotely, or runs
disruptive commands.

## Secrets

- Stored using the OS credential store where practical (interface reserved;
  Phase 1 avoids storing raw secrets at all).
- Redacted from logs, prompt records, reports, event streams, and error
  messages (`_redact` in `buster/permissions/audit.py`,
  `buster/prompts/service.py`).

## Network exposure

- The web server binds to `127.0.0.1` by default.
- LAN binding is only enabled after explicit onboarding approval and requires a
  token (`server.lan_token`). Buster is never exposed unauthenticated to the
  wider network.
- No aggressive port scanning by default; any broader scan requires explicit
  user approval and a stated scope.

## Discovery & nodes

- Discovery is **read-only**. Buster never connects to a discovered service or
  node automatically.
- Trust is an explicit, per-scope user decision (discovered → trusted →
  workspace → administrative). No node inherits another node's permissions.
- Cross-node delegation is deferred; read-only delegated tasks (future) return
  data only and can never cause Buster to run a system-changing action.

## External runtimes (Hermes, OpenClaw, …)

- Detection is read-only. Submitting executable tasks to real external runtimes
  is disabled by default (`runtimes.allow_task_submission = false`).
- Buster never imports credentials, memory, history, permissions, schedules,
  trusted nodes, or API keys automatically. Each is a separate user approval.
- External runtime permissions never bypass Buster's action/safety rules.

## Audit

Every tool run, model call, permission decision, and action is appended to
`audit_log` with timestamp, workspace, task, risk level, approval, result,
model, inference location, and whether external data was shared.
