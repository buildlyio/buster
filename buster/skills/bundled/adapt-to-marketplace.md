---
id: adapt-to-marketplace
name: Adapt app to the Forge marketplace
description: Add Buildly Forge/marketplace structure to an existing repository, using the adoption scan.
tools:
  - core.capabilities
context:
  - system
permissions:
  - write
---

Help the user prepare an EXISTING application for the Buildly Forge marketplace.
Additive and non-destructive — never modifies application code.

1. Run a non-destructive adoption scan first (`buster adopt`) to understand the
   app: frameworks, routes, models, tests. Review the inferred summary.
2. Add the Forge structure with `buster forge adapt` — writes BUILDLY.yaml,
   .ai/AGENT_POLICY.md, and devdocs/ templates only where they are missing.
   Existing files are left untouched.
3. Help the user fill in the marketplace manifest (name, description ≤160 chars,
   category, tags, author, repository, license).
4. Point out what the marketplace expects: screenshots under
   marketplace/screenshots/, a clear README, and passing tests.
5. Approvals turn inferred feature boundaries into contracts (later phase);
   inferred items never become product truth automatically.

Keep it lightweight; do not require Labs connectivity.
