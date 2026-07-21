# Database & Migrations

Buster uses a single SQLite database (`data/buster.db`) in WAL mode with a
single controlled writer. No separate database server, graph DB, or vector DB.

## Access pattern

- **Reads** use short-lived connections (WAL allows concurrent readers).
- **Writes** are serialized through one writer connection guarded by a lock
  (`buster/database/db.py`), avoiding `database is locked` under the in-process
  job queue.

## Migrations

Migrations live in `buster/database/migrations.py` as an ordered list of
`(target_version, sql)` and are applied via `PRAGMA user_version`. On startup
`Database.migrate()` applies any migration whose target exceeds the current
version.

Rules:
- Never rewrite a shipped migration; add a new `(version, sql)` entry.
- Use `IF NOT EXISTS` for forward-friendliness.
- Record notes below for each version.

### v1 — initial Phase 1 schema

Tables: `workspaces`, `conversations`, `messages`, `tasks`, `task_events`,
`reports`, `research_projects`, `sources`, `memories` (+ `memories_fts` FTS5),
`documents`, `document_chunks` (with reserved `embedding` blob for a future
semantic index), `diagnostic_runs`, `alerts`, `tools`, `skills`, `permissions`,
`actions`, `services`, `nodes`, `runtimes`, `prompt_records` (+ `prompts_fts`),
`cache_entries`, `personality_changes`, `audit_log`.

## Full-text search

`memories_fts` and `prompts_fts` are FTS5 external-content tables kept in sync by
triggers. Retrieval uses `bm25()` ranking with a `LIKE` fallback for queries
that contain FTS-special characters.

## Semantic index (deferred)

`document_chunks.embedding` is reserved for a future SQLite vector index. Phase 1
does not require vector search; the interface exists so it can be added without a
schema break.
