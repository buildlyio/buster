# Prompt Library Schema

Buster keeps a first-class record of prompts that create, edit, or materially
affect product features, issues, architecture, code, testing, docs, or releases.

## Record

```yaml
id: prompt_01
title: Implement local Buster discovery
workspace: buildly
product: buster

linked_items:
  features: []
  issues: []

source:
  interface: cli            # cli | web
  provider: ollama
  model: qwen2.5:7b
  inference_location: device   # device | lan | remote

content:
  original_prompt: <the user's original prompt>
  resolved_context: <context Buster added automatically>
  final_prompt: <the prompt actually executed>

outcome:
  status: draft            # draft | applied | …
  summary: null
  files_changed: []
  commit: null
  pull_request: null

tags: [discovery, python]
visibility: private        # private | workspace | community  (default private)
is_template: false
```

Original prompt, added context, and final prompt are stored **separately**.
Secrets in `source` are redacted before storage.

## Capabilities (Phase 1)

- Save, list, search (FTS5), view, tag, link to a placeholder feature/issue,
  export as Markdown, mark as reusable template.
- Community sharing is deferred; the `visibility` field exists and defaults to
  `private`.

## Interfaces

CLI:

```sh
buster prompts                       # list
buster prompts save "Title" --prompt "..."
buster prompts search "network discovery"
buster prompts show <id>
```

API:

```
GET  /api/prompts
POST /api/prompts
GET  /api/prompts/search?q=...
GET  /api/prompts/{id}
```
