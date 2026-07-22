# User Installation Guide

## One-line install (macOS / Linux)

```sh
curl -fsSL https://install.buster.buildly.io | sh
```

Or from a checkout:

```sh
./install.sh
```

The installer will:

1. Detect your OS and architecture.
2. Check for Python 3.11+ (and install `uv` if permitted).
3. Install Buster into an isolated environment (`~/.buster/venv`).
4. Create data/config/cache directories.
5. Install a user-level background service (`launchd` on macOS,
   `systemd --user` on Linux) — **no root required**.
6. Start Buster and put the `buster` command on your PATH.

When it finishes you'll see:

```
Buster is running.

CLI:       buster
Web:       http://buster.local
Fallback:  http://localhost:8765
Status:    buster status

Inference policy: Local first
```

If `buster.local` isn't available on your network, the `localhost` URL always
works.

## First steps

```sh
buster                 # interactive assistant
buster system status   # what your machine can support
buster doctor          # check Buster's own health
buster open            # open the web interface
```

## Hostnames on a shared LAN

Each Buster node advertises a unique `<node>.buster.local` name over mDNS (plus a
bare `buster.local` alias), so multiple Busters coexist without colliding.
`localhost` always works too.

If your network uses a local DNS server (e.g. Pi-hole) with a `.home` suffix:

```toml
[server]
domain = "buster.home"
```

Then run `buster doctor` — it prints the exact A records (e.g.
`alderaan.buster.home → <ip>` and `buster.home → <ip>`) to add in Pi-hole. Buster
never edits your DNS. See the README's "Hostnames & local DNS" section for detail.

## Local inference

Buster prefers a model on **this** device. Install [Ollama](https://ollama.com)
and pull a model sized for your hardware (see `buster system status` for the
recommended class), e.g.:

```sh
ollama pull gemma3        # or a smaller model on low-RAM devices
```

Have models on another machine? Add it as a trusted LAN endpoint in your config:

```toml
[inference]
lan_ollama_urls = ["http://your-server.local:11434"]
```

Buster stays useful with no model at all — diagnostics, discovery, alerts,
memory search, and caching all work without an LLM.

## Managing the service

```sh
buster start | stop | restart | status | logs
buster update
```

## Uninstalling

```sh
buster uninstall            # stop + remove the service, venv, and CLI shim; KEEP data
buster uninstall --purge    # also delete reports, memory, and config (irreversible)
buster uninstall --keep-program   # only remove the service, leave the venv/CLI in place
```

Or, if the CLI isn't on your PATH (or the venv is already gone), run the script
from a checkout:

```sh
./uninstall.sh              # keeps data
./uninstall.sh --purge      # deletes data too
```

Either path unloads the launchd (macOS) / systemd (Linux) user service, removes
`~/.buster/venv` and the `buster` shim, and — only with `--purge` — deletes the
data directory. Both are idempotent and safe to re-run.

## Privacy

By default Buster uses local inference first and asks before sending content
outside your local network. The web server listens on localhost only until you
explicitly enable LAN access during onboarding.
