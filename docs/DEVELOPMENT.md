# Developer Setup

## Requirements

- Python 3.11+ (3.12/3.13 recommended)
- (Optional) [Ollama](https://ollama.com) for local inference, or a reachable
  LAN Ollama endpoint
- (Optional) [uv](https://astral.sh/uv) for faster installs

## Setup

```sh
git clone https://github.com/buildlyio/buster
cd buster
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Buster stores everything under a home directory (see `buster config`). For
development, isolate it:

```sh
export BUSTER_HOME="$PWD/.busterhome"
```

## Run

```sh
# foreground server (what the service runs)
.venv/bin/python -m buster.main serve

# or via the CLI
.venv/bin/buster start
.venv/bin/buster status
.venv/bin/buster open        # open the web UI
```

Web UI: `http://localhost:8765` (or the configured port).

## Configure a LAN model

If your models live on another machine (e.g. `alderaan.home`):

```sh
# config.toml
[inference]
lan_ollama_urls = ["http://alderaan.home:11434"]
default_model = "gemma3:latest"
```

Buster routes to the device first, then trusted LAN endpoints. Chat responses
report the inference location and whether data left the machine/network.

## Tests

```sh
.venv/bin/python -m pytest -q
```

Tests use an isolated `BUSTER_HOME`, mock model providers and external services,
and require **no internet**.

## Layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the module map. Key entry points:

- `buster/api/app.py` — FastAPI app factory
- `buster/api/routes.py` — Core REST API + SSE
- `buster/cli/main.py` — Typer CLI
- `buster/agent/loop.py` — bounded agent loop
- `buster/tools/packs/` — tool packs
- `buster/skills/bundled/` — bundled skills

## Adding a tool

```python
from pydantic import BaseModel
from buster.tools.registry import tool

class Args(BaseModel):
    limit: int = 20

class Result(BaseModel):
    items: list[str]

@tool(id="mypack.thing", description="…", pack="mypack",
      permission="read", risk_level=0)
async def thing(args: Args) -> Result:
    return Result(items=[...])
```

Then add `"buster.tools.packs.mypack"` to `_BUILTIN_PACKS` in
`buster/tools/registry.py`.
