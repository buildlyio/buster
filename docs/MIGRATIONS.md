# Migration Notes

Migrations are applied automatically on startup via `PRAGMA user_version`.
See [DATABASE.md](DATABASE.md) for the mechanism.

## v1 (0.1.0)

Initial Phase 1 schema. No upgrade path needed — a fresh install starts here.
Creates all core tables plus `memories_fts` and `prompts_fts` FTS5 indexes.

To add a migration:

1. Append `(N, "…SQL…")` to `MIGRATIONS` in `buster/database/migrations.py`.
2. Never edit an already-shipped block.
3. Document the change here with the release version.

## History

- **v1** — full Phase 1 schema.
- **v2** (Phase 2.1) — `runtime_runs` table: audit record of delegated tasks
  submitted to agent runtimes (Hermes/OpenClaw/CLI), including status, output,
  model, inference location, and data-sharing flag.
