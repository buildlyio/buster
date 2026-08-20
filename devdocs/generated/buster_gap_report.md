# Buster Diagnostic & Gap Report

Generated: 2026-08-13

## Quick results

- Diagnostic (`diagnostics/check_buster_env.py`):
  - MCP available: True
  - MCP auth state: LabsAuthState.UNREACHABLE
  - Runtimes detected: `buster` (running), `hermes` (detected), `openclaw` (detected)

- Test suite: `pytest` → 154 passed, 1 warning (no network required).

## Current integration state

- Buster speaks to Buildly MCP via `buster/buildly/mcp_client.py` (SSE or local stdio transports).
- The `BuildlyAdapter` used by the app is currently a Phase‑1 mock (`buster/buildly/adapter.py`).
- `BuildlyDevelopmentService` defines local repo inspection, adoption scan, and context packaging; Phase‑1 includes local, read-only implementations.
- Hosted model provider for Anthropic (Claude) exists (`buster/models/anthropic.py`) under the gated-remote path.
- Runtimes for Hermes/OpenClaw are detected (adapters in `buster/runtimes/adapters.py`) and mocked where not present.
- Memory is Markdown + SQLite FTS5 (`buster/memory/service.py`) with snippet-based retrieval (`buster/context/builder.py`).

## Observed gaps & recommended next work (prioritized)

1. Wire a real `BuildlyAdapter` backed by `BuildlyMcpClient`:
   - Create `BuildlyMcpAdapter` implementing `BuildlyAdapter` and using `mcp_client` tool names (`buildly_get_*`, `buildly_create_*`).
   - Switch selection in `get_buildly_adapter()` to return the real adapter when `config.buildly.mode` is `local_mcp` or `hosted_mcp`.
   - Add robust error handling and mapping tests for returned MCP payload shapes (use existing `_items()` helpers).

2. Enable a local bb-agent-manager run for integration testing:
   - Clone https://github.com/Buildly-Labs/bb-agent-manager and start it locally per its README (recommended: in a container or local dev venv).
   - Point Buster at it via `buildly.mcp_url` (SSE) or `buildly.mcp_local_command` (stdio launcher) in your config.
   - Re-run `diagnostics/check_buster_env.py` to confirm `LabsAuthState.OK` or expected auth state.

3. Implement controlled task submission and runtime adapters:
   - Extend runtime adapters to support `submit(stream/cancel/logs)` as described in `docs/PHASE2.md`.
   - Implement strict CLI subprocess allow-list and size/timeouts for Hermes/OpenClaw CLI submission.
   - Add `runtime_runs` audit table and normalize events into Buster event bus.

4. Local-first LLM integration & orchestration:
   - Add adapters for local models (Ollama, locally-hosted LLMs) as `ModelProvider` implementations.
   - Ensure gated-remote policy applies uniformly; label `external_data_shared=True` on hosted responses and audit them.

5. Memory & long-term project learning:
   - Define retention policies and an API for programmatic memory writes (e.g., when saving context packages or adopted changes).
   - Consider summarization/compaction jobs to keep token budgets bounded.

6. Developer DX: bb-code & tokenjam integration
   - Register `bb-code` and `tokenjam` as CLI runtimes if present and surface their outputs read-only in the Dev UI.
   - Add guided `dev setup` flows already referenced in `docs/PHASE2.md`.

## How to run the environment locally (quick commands)

1. Install dev deps (already done in this session):

```bash
.venv/bin/python -m pip install -e '.[dev]'
```

2. Run the diagnostics (already executed):

```bash
.venv/bin/python diagnostics/check_buster_env.py
```

3. Run tests:

```bash
.venv/bin/python -m pytest -q
```

4. To point Buster at a running bb-agent-manager (hosted or local), set config (edit `config/example` or your saved config):

- In `config.example.toml` or your config file, set:

```toml
[buildly]
mode = "hosted_mcp"       # or "local_mcp"
mcp_url = "http://localhost:4380/sse"
# or for a local stdio launcher
mcp_local_command = "bb-agent-manager"
```

## Suggestions for next hands-on steps (I can do these)

- Implement and test `BuildlyMcpAdapter` that maps MCP tool responses to `BuildlyAdapter` models. (I can scaffold this and tests.)
- Start a local `bb-agent-manager` instance and run an end-to-end integration test: real auth probe, list products, create and bind a product.
- Add `runtime.submit` support for Hermes/OpenClaw and add end-to-end test coverage.

If you want, I can scaffold the `BuildlyMcpAdapter` and a small integration test next.