# ForgeAppTemplate — AI-Native alignment (proposed)

Proposed, non-breaking changes to
[Buildly-Marketplace/ForgeAppTemplate](https://github.com/Buildly-Marketplace/ForgeAppTemplate)
so it reflects the AI-native product-development workflow and works cleanly with
Buster (`buster forge new`, `buster forge adapt`, `buster adopt`).

The template is already well-aligned (it has `.ai/`, `devdocs/{features,bugs,reviews}`,
`BUILDLY.yaml`). These changes are additive and small.

## Proposed changes

1. **`.gitignore` — decide what Buster-generated state is tracked.**
   Buster's adoption scan writes human-readable, Git-trackable drafts under
   `devdocs/generated/` (keep tracked) and machine state under `.buildly/`
   (ignore the volatile parts). Add:
   ```gitignore
   # Buildly / Buster workflow state
   .buildly/sync/pending/
   .buildly/adoption/*.json
   ```
   Keep `devdocs/generated/*.md` tracked (they're durable, reviewable docs).

2. **README — a short "AI-native workflow with Buster" section.**
   Explain that a user can:
   - `buster forge new <name>` to start from this template's structure, or
   - `buster adopt` + `buster forge adapt` to bring an existing app to the
     marketplace,
   and that Labs connectivity is optional/offline-friendly.

3. **`devdocs/generated/.gitkeep`** — establish the directory the adoption scan
   and doc generation write into, so it exists in a fresh clone.

4. **`.ai/AGENT_POLICY.md`** — add two lines matching Buster's guarantees:
   inferred conclusions are proposals until a human approves them; no auto-merge.

## Non-goals

- No change to the test tooling (Robot Framework), CI, or app structure.
- No new runtime dependency.
- No requirement to install Buster to use the template.

## Status

Draft for review. The PR will be opened on the ForgeAppTemplate repo only after
sign-off, since it's a separate public repository others depend on.
