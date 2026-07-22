---
id: new-forge-app
name: New Forge app
description: Scaffold a new Buildly Forge marketplace app (structure + manifest), optionally with a FastAPI module.
tools:
  - core.capabilities
context:
  - system
permissions:
  - write
---

Help the user start a new Buildly Forge app. Local-first and offline-capable.

1. Ask for the app name and a one-line description.
2. Create the Forge structure with `buster forge new` (BUILDLY.yaml manifest,
   .ai/AGENT_POLICY.md, devdocs/{features,bugs,reviews}, marketplace/screenshots).
3. Offer to scaffold a first service with `buster scaffold "<name>" --models a,b`
   (FastAPI + SQLAlchemy CRUD module that runs immediately).
4. Explain next steps: fill in BUILDLY.yaml author/repository, add screenshots,
   and connect to Buildly Labs when ready (never required).

Never overwrite existing files. Keep it fast and minimal.
