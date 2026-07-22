"""Ordered SQL migrations, applied via ``PRAGMA user_version``.

Each entry is ``(target_version, sql)``. Migrations are idempotent-friendly
(``IF NOT EXISTS``) and never rewritten once shipped — add a new entry instead.
Migration notes live in docs/MIGRATIONS.md.
"""

from __future__ import annotations

# --- v1: full Phase 1 schema -------------------------------------------------

_V1 = """
CREATE TABLE IF NOT EXISTS workspaces (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'local',   -- local | buildly
    created_at  TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    workspace   TEXT NOT NULL DEFAULT 'default',
    title       TEXT NOT NULL DEFAULT 'Conversation',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,   -- user | assistant | system | tool
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    metadata        TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    workspace   TEXT NOT NULL DEFAULT 'default',
    kind        TEXT NOT NULL,      -- chat | research | diagnostic | action | ...
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'created',  -- created|running|completed|failed|cancelled
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, created_at);

CREATE TABLE IF NOT EXISTS task_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT,
    type        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    timestamp   TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, id);
CREATE INDEX IF NOT EXISTS idx_events_type ON task_events(type, id);

CREATE TABLE IF NOT EXISTS reports (
    id          TEXT PRIMARY KEY,
    workspace   TEXT NOT NULL DEFAULT 'default',
    title       TEXT NOT NULL,
    slug        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'research',
    path        TEXT NOT NULL,        -- markdown file path
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    metadata    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS research_projects (
    id          TEXT PRIMARY KEY,
    workspace   TEXT NOT NULL DEFAULT 'default',
    question    TEXT NOT NULL,
    slug        TEXT NOT NULL,
    dir         TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    publisher       TEXT NOT NULL DEFAULT '',
    author          TEXT NOT NULL DEFAULT '',
    published_at    TEXT NOT NULL DEFAULT '',
    retrieved_at    TEXT NOT NULL,
    content_hash    TEXT NOT NULL DEFAULT '',
    text_path       TEXT NOT NULL DEFAULT '',
    trust           TEXT NOT NULL DEFAULT 'unrated',
    notes           TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id);

CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    workspace       TEXT NOT NULL DEFAULT 'default',
    path            TEXT NOT NULL,
    heading_path    TEXT NOT NULL DEFAULT '',
    text            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    modified_at     TEXT NOT NULL,
    importance      INTEGER NOT NULL DEFAULT 3,
    retention       TEXT NOT NULL DEFAULT 'durable',
    token_estimate  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_memories_path ON memories(path);

-- FTS5 over memory text for retrieval.
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    text, heading_path, path UNINDEXED, content='memories', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, text, heading_path, path)
    VALUES (new.rowid, new.text, new.heading_path, new.path);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, text, heading_path, path)
    VALUES ('delete', old.rowid, old.text, old.heading_path, old.path);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, text, heading_path, path)
    VALUES ('delete', old.rowid, old.text, old.heading_path, old.path);
    INSERT INTO memories_fts(rowid, text, heading_path, path)
    VALUES (new.rowid, new.text, new.heading_path, new.path);
END;

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    workspace   TEXT NOT NULL DEFAULT 'default',
    path        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    ordinal     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    -- reserved for future semantic index (vector blob); unused in Phase 1
    embedding   BLOB,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS diagnostic_runs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,   -- system | network
    status      TEXT NOT NULL,   -- ok | warning | critical
    created_at  TEXT NOT NULL,
    results     TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS alerts (
    id          TEXT PRIMARY KEY,
    code        TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'warning',
    title       TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(acknowledged, created_at);

CREATE TABLE IF NOT EXISTS tools (
    id          TEXT PRIMARY KEY,
    pack        TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    permission  TEXT NOT NULL DEFAULT 'read',
    risk_level  INTEGER NOT NULL DEFAULT 0,
    platforms   TEXT NOT NULL DEFAULT '[]',
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS skills (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    path        TEXT NOT NULL,
    tools       TEXT NOT NULL DEFAULT '[]',
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS permissions (
    id          TEXT PRIMARY KEY,
    task_id     TEXT,
    action_id   TEXT,
    risk_level  INTEGER NOT NULL,
    summary     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'requested',  -- requested|approved|denied
    created_at  TEXT NOT NULL,
    decided_at  TEXT,
    decided_by  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS actions (
    id          TEXT PRIMARY KEY,
    task_id     TEXT,
    title       TEXT NOT NULL,
    risk_level  INTEGER NOT NULL,
    plan        TEXT NOT NULL DEFAULT '{}',   -- structured plan
    status      TEXT NOT NULL DEFAULT 'proposed', -- proposed|approved|denied|running|verified|failed
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    result      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS services (
    id              TEXT PRIMARY KEY,   -- lcdp id
    name            TEXT NOT NULL,
    product         TEXT NOT NULL DEFAULT '',
    version         TEXT NOT NULL DEFAULT '',
    host            TEXT NOT NULL DEFAULT '',
    manifest        TEXT NOT NULL DEFAULT '{}',
    trust           TEXT NOT NULL DEFAULT 'discovered',  -- discovered|trusted|workspace|ignored
    discovered_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    device_type     TEXT NOT NULL DEFAULT '',
    platform        TEXT NOT NULL DEFAULT '',
    api_url         TEXT NOT NULL DEFAULT '',
    manifest        TEXT NOT NULL DEFAULT '{}',
    trust           TEXT NOT NULL DEFAULT 'discovered',
    discovered_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtimes (
    id              TEXT PRIMARY KEY,
    runtime_type    TEXT NOT NULL,      -- buster|hermes|openclaw|mcp|cli
    name            TEXT NOT NULL,
    detected_via    TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'detected',
    manifest        TEXT NOT NULL DEFAULT '{}',
    trust           TEXT NOT NULL DEFAULT 'detected',
    discovered_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_records (
    id              TEXT PRIMARY KEY,
    workspace       TEXT NOT NULL DEFAULT 'default',
    title           TEXT NOT NULL,
    product         TEXT NOT NULL DEFAULT '',
    linked_items    TEXT NOT NULL DEFAULT '{}',
    source          TEXT NOT NULL DEFAULT '{}',
    original_prompt TEXT NOT NULL DEFAULT '',
    resolved_context TEXT NOT NULL DEFAULT '',
    final_prompt    TEXT NOT NULL DEFAULT '',
    outcome         TEXT NOT NULL DEFAULT '{}',
    tags            TEXT NOT NULL DEFAULT '[]',
    visibility      TEXT NOT NULL DEFAULT 'private',  -- private|workspace|community
    is_template     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS prompts_fts USING fts5(
    title, original_prompt, tags, content='prompt_records', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS prompts_ai AFTER INSERT ON prompt_records BEGIN
    INSERT INTO prompts_fts(rowid, title, original_prompt, tags)
    VALUES (new.rowid, new.title, new.original_prompt, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS prompts_ad AFTER DELETE ON prompt_records BEGIN
    INSERT INTO prompts_fts(prompts_fts, rowid, title, original_prompt, tags)
    VALUES ('delete', old.rowid, old.title, old.original_prompt, old.tags);
END;

CREATE TABLE IF NOT EXISTS cache_entries (
    key         TEXT PRIMARY KEY,
    namespace   TEXT NOT NULL,
    file_path   TEXT,
    value       TEXT,
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    expires_at  TEXT,
    content_hash TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_cache_ns ON cache_entries(namespace);
CREATE INDEX IF NOT EXISTS idx_cache_exp ON cache_entries(expires_at);

CREATE TABLE IF NOT EXISTS personality_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field       TEXT NOT NULL,
    old_value   TEXT NOT NULL DEFAULT '',
    new_value   TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    user        TEXT NOT NULL DEFAULT '',
    workspace   TEXT NOT NULL DEFAULT 'default',
    task_id     TEXT,
    category    TEXT NOT NULL,   -- tool|model|permission|action|discovery|buildly
    detail      TEXT NOT NULL DEFAULT '{}',
    risk_level  INTEGER,
    approved    INTEGER,
    result      TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    inference_location TEXT NOT NULL DEFAULT '',
    external_data_shared INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
"""

# --- v2: delegated runtime runs (Phase 2 task routing) ----------------------

_V2 = """
CREATE TABLE IF NOT EXISTS runtime_runs (
    run_id              TEXT PRIMARY KEY,
    runtime_id          TEXT NOT NULL,
    runtime_type        TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'queued',
    prompt              TEXT NOT NULL DEFAULT '',
    output              TEXT NOT NULL DEFAULT '',
    error               TEXT NOT NULL DEFAULT '',
    model               TEXT NOT NULL DEFAULT '',
    inference_location  TEXT NOT NULL DEFAULT 'unknown',
    external_data_shared INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runtime_runs ON runtime_runs(runtime_id, created_at);
"""

MIGRATIONS: list[tuple[int, str]] = [
    (1, _V1),
    (2, _V2),
]
