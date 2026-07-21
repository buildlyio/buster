# Local Capability Discovery Protocol (LCDP) — v1 draft

LCDP is an open, lightweight way for local applications and services to
advertise what they are and what they can do, so assistants like Buster can
discover them **without connecting automatically**.

## Goals

- Read-only discovery: finding a service reveals a manifest, nothing more.
- Human-in-the-loop trust: connection and trust are explicit user decisions.
- Transport-agnostic: works over mDNS/DNS-SD, a well-known HTTP path, a local
  registry, or a manually configured URL.

## Manifest

Served at `/.well-known/lcdp.json` (or advertised via mDNS TXT records pointing
to it):

```json
{
  "schema": "lcdp/v1",
  "id": "launchpad.local",
  "name": "Buildly Launchpad",
  "product": "launchpad",
  "version": "0.8.0",
  "api_url": "http://localhost:4380/api",
  "health_url": "http://localhost:4380/health",
  "mcp_url": "http://localhost:4380/mcp",
  "capabilities": ["process.status", "process.logs"],
  "authentication": "local-token",
  "permissions": ["read", "execute-with-confirmation"]
}
```

### Fields

| Field | Meaning |
|---|---|
| `schema` | Always `lcdp/v1`. |
| `id` | Stable unique id (host-scoped). |
| `name` / `product` / `version` | Human + machine identity. |
| `api_url` / `health_url` / `mcp_url` | Optional endpoints. |
| `capabilities` | Dotted capability names the service offers. |
| `authentication` | `none` \| `local-token` \| … |
| `permissions` | Permission categories (`read`, `execute-with-confirmation`, …). |

### Buster node extension

Buster advertises the base manifest plus:

```json
{
  "device_type": "workstation",
  "platform": "macos",
  "models": ["gemma3:latest"],
  "skills": ["quick-web-research"],
  "toolpacks": ["system_diagnostics"],
  "allowed_workloads": ["capability_query"],
  "trust_requirements": "manual"
}
```

## Discovery mechanisms

1. **mDNS / DNS-SD** — browse `_http._tcp.local.`, probe candidates for the
   well-known path. (Best-effort; optional.)
2. **`/.well-known/lcdp.json`** — direct HTTP fetch.
3. **Local service registry** — future.
4. **Manually configured URLs** — `discovery.service_urls` in config.

## Trust model

Discovery classifies a manifest as a **service** (generic) or a **node**
(`product == "buster"`). Both start at trust `discovered`. The user chooses:

- Connect once
- Trust this service
- Trust only for this workspace
- Ignore
- Show capabilities

Buster never connects automatically and no node inherits another's permissions.

## Buster's own manifest

`GET /api/discovery/manifest` returns this node's LCDP manifest so other Buster
instances can discover it.
