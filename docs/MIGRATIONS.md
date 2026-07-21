# Migration Notes

Migrations are applied automatically on startup via `PRAGMA user_version`.
See [DATABASE.md](DATABASE.md) for the mechanism.

## v1 (0.1.0)

Initial Phase 1 schema. No upgrade path needed — a fresh install starts here.
Creates all core tables plus `memories_fts` and `prompts_fts` FTS5 indexes.

To add a migration:

1. Append `(2, "…SQL…")` to `MIGRATIONS` in `buster/database/migrations.py`.
2. Never edit the v1 block.
3. Document the change here with the release version.
