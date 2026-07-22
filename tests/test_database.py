from buster.database import get_database
from buster.database.migrations import MIGRATIONS

LATEST = MIGRATIONS[-1][0]


def test_migrations_apply():
    db = get_database()
    assert db.schema_version == LATEST


def test_tables_exist():
    db = get_database()
    rows = db.query("SELECT name FROM sqlite_master WHERE type='table'")
    names = {r["name"] for r in rows}
    for t in ("workspaces", "conversations", "messages", "tasks", "reports",
              "sources", "memories", "alerts", "actions", "services", "nodes",
              "runtimes", "runtime_runs", "prompt_records", "cache_entries", "audit_log"):
        assert t in names, f"missing table {t}"


def test_migrate_idempotent():
    db = get_database()
    assert db.migrate() == LATEST
    assert db.migrate() == LATEST  # re-running does nothing


def test_write_read():
    db = get_database()
    db.execute("INSERT INTO workspaces (id, name, created_at) VALUES ('w1','W','2026')")
    row = db.query_one("SELECT name FROM workspaces WHERE id='w1'")
    assert row["name"] == "W"
