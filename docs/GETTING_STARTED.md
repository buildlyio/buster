# Getting started with Buster 🐰

Buster is a local-first assistant: it prefers models on your own machine, keeps
your data local, and asks before doing anything that changes your system. This
guide gets you from install to a working assistant in a few minutes.

> In the terminal you can run `buster guide` to see a short version of this any time.

---

## 1. Install

```sh
curl -fsSL https://install.buster.buildly.io | sh   # macOS / Linux
# …or from a checkout:  ./install.sh
```

The installer starts Buster as a background service, puts `buster` on your PATH,
and runs provider setup. When it finishes you'll see the API and Web URLs.

## 2. Connect a model

Buster needs a model to chat and research (diagnostics, discovery, and memory
work without one). Run:

```sh
buster setup
```

It detects Ollama / LM Studio on **this machine** and, if you allow it, scans
your **local network** for a model server (e.g. another box running Ollama).
Pick one and Buster sends a tiny test prompt to confirm the model actually
responds — you'll see **✓ AI connected and working** or a clear reason if not.

- No local models? Install one: `ollama pull gemma3` (or a smaller model on
  low-RAM machines — `buster system status` shows what your hardware supports).
- Models live on another machine? The network scan finds them; or add the
  endpoint under `[inference] lan_ollama_urls` in your config.
- Want a hosted model (Claude/OpenAI)? Opt in under `[inference.remote]`. It's
  off by default and every off-network response is labelled and audited.

## 3. Chat and research

```sh
buster                              # interactive assistant
buster ask "what can you do?"       # one-off question
buster research "a topic"           # web research → a local Markdown report
buster reports                      # list saved reports
```

Every reply shows the model, where it ran (device / lan / remote), and whether
any data left your machine.

## 4. System & network checks (no model needed)

```sh
buster doctor          # is Buster itself healthy?
buster system check    # CPU, memory, disk, Ollama, …
buster network check   # DNS, gateway, internet, reachability
buster alerts          # open alerts
```

## 5. Developer workflow (optional)

If you build software, Buster can act as a development coordinator:

```sh
buster dev             # detected dev tools (bb-code, TokenJam, Ollama)
buster dev setup       # register bb-code as a runtime; guide optional installs
buster adopt           # non-destructive scan of an existing repo
buster approve <id>    # turn an inferred finding into a local contract
buster labs connect http://bb-agent.home/sse   # connect Buildly Labs (via MCP)
buster labs status     # is Labs connected & authenticated?
buster work <issue>    # build a bounded context package, optionally run an agent
buster sync            # push approved contracts to Labs (offline-safe)
```

Buster never modifies your application files during a scan, never auto-approves
inferred findings, and never auto-merges pull requests.

## 6. Manage the service

```sh
buster status | start | stop | restart | logs
buster open            # open the web UI
buster update          # check for and install a newer release
buster uninstall       # clean removal (add --purge to delete data)
```

---

## Troubleshooting

| Symptom | Try |
|---|---|
| "No model provider set up" | `buster setup` |
| Chat errors / model not responding | `buster doctor`, then `buster setup` to re-pick |
| `buster.local` doesn't resolve | use `http://localhost:<port>`; for a `.home` domain add a DNS record (see [INSTALL](INSTALL.md)) |
| Labs shows "token invalid" | `buster labs login` to refresh the token |
| Service won't start on the default port | the installer auto-picks a free port; see `buster status` |

More: [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [Install guide](INSTALL.md)

Brought to you by [buildly.io](https://buildly.io) — Build Smarter, Not Harder.
