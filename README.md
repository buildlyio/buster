# Buster

**Buster** is a lightweight, hardware-adaptive, local-first assistant for
research, reporting, machine diagnostics, network monitoring, and safe action —
from Buildly. It runs on macOS and Linux, from Raspberry Pi-class devices up to
GPU workstations, and adapts to the hardware and services around it.

Buster prefers models running on the current device, discovers the capabilities
in its environment, and only reaches out to the local network or remote services
when necessary and permitted. It stays useful even when no language model is
loaded — monitoring, discovery, alerts, diagnostics, caching, and scheduling all
run deterministically.

## Quick start

```sh
# One-line install (macOS / Linux)
curl -fsSL https://install.buster.buildly.io | sh

# Or from a checkout
./install.sh
```

After install:

```
Buster is running.

CLI:       buster
Web:       http://buster.local
Fallback:  http://localhost:8765
Status:    buster status

Inference policy: Local first
```

## CLI

```sh
buster                      # interactive mode
buster ask "question"
buster research "topic"
buster reports
buster system check
buster network check
buster doctor               # inspect Buster itself
buster nodes
buster services
buster prompts
buster config
```

Full command list: `buster --help`.

## Principles

1. **Local first** — prefer on-device models; ask before sending content
   outside the local network.
2. **Hardware adaptive** — detect the machine and adapt; Raspberry Pi is the
   minimum tier, not the design center.
3. **Lightweight at rest** — Python + SQLite + Markdown + filesystem. No
   mandatory Docker, Kubernetes, Redis, Postgres, or Node.js on the target.
4. **User control** — Buster distinguishes observation, interpretation,
   recommendation, proposed action, approved action, and verified result. It
   never silently changes your system or sends data remotely.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security model](docs/SECURITY.md)
- [LCDP specification draft](docs/LCDP.md)
- [Database & migrations](docs/DATABASE.md)
- [Developer setup](docs/DEVELOPMENT.md)
- [User installation guide](docs/INSTALL.md)
- [Roadmap](docs/ROADMAP.md)

## License

MIT © Buildly
