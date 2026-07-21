"""Interactive CLI mode.

Streaming responses, real-time task activity, permission prompts, Markdown
rendering, slash commands, and a clear inference-location display.
"""

from __future__ import annotations

import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from buster import __version__
from buster.cli import service as svc
from buster.config import load_config

_HELP = """[bold]Slash commands[/]
  /help              show this help
  /system            run a system health check
  /network           run a network health check
  /research <topic>  run web research
  /reports           list reports
  /nodes             list discovered nodes
  /alerts            list open alerts
  /doctor            inspect Buster itself
  /workspace         switch/show workspace
  /quit              exit
"""


def _banner(console: Console) -> None:
    config = load_config()
    model = "no model"
    system = "unknown"
    nodes = 0
    try:
        with httpx.Client(timeout=3.0) as c:
            st = c.get(f"{config.base_url}/api/status").json()
            model = st["models"][0]["name"] if st["models"] else "no model"
            nodes = st["trusted_nodes"]
        with httpx.Client(timeout=3.0) as c:
            doc = c.get(f"{config.base_url}/api/doctor").json()
            system = {"ok": "Healthy", "warning": "Degraded", "critical": "Problems"}.get(doc["status"], "Unknown")
    except Exception:  # noqa: BLE001
        pass
    console.print(Panel(
        f"[bold]Buster[/] {__version__}\n"
        f"Local model: [cyan]{model}[/]\n"
        f"System: {system}\n"
        f"Trusted nodes: {nodes}\n"
        f"[dim]Inference policy: {config.inference.policy} · type /help[/]",
        title="🐶 Buster"))


def run_interactive(console: Console) -> None:
    if not svc.status()["api_reachable"]:
        console.print("[yellow]Service not running.[/] Start it with [bold]buster start[/] for full features.")
        console.print("[dim]Offline commands like /doctor, /system, /network still work.[/]\n")

    _banner(console)
    config = load_config()

    while True:
        try:
            line = console.input("\n[bold green]You ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye.")
            return
        if not line:
            continue
        if line.startswith("/"):
            if _handle_slash(console, line, config):
                return
            continue
        _ask(console, config, line)


def _ask(console: Console, config, prompt: str) -> None:
    try:
        with console.status("[dim]Buster is working…[/]"):
            with httpx.Client(timeout=180.0) as c:
                r = c.post(f"{config.base_url}/api/ask", json={"prompt": prompt}).json()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error:[/] {exc}")
        return
    console.print("\n[bold cyan]Buster ›[/]")
    console.print(Markdown(r.get("content") or "_(no content)_"))
    console.print(f"[dim]{r['model']} · {r['inference_location']} · "
                  f"data left machine: {'yes' if r['external_data_shared'] else 'no'}"
                  f"{' · tools: ' + ', '.join(r['tools_used']) if r['tools_used'] else ''}[/]")


def _handle_slash(console: Console, line: str, config) -> bool:
    """Return True to exit."""
    parts = line[1:].split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("quit", "exit", "q"):
        return True
    if cmd == "help":
        console.print(_HELP)
    elif cmd == "doctor":
        import asyncio

        from buster.diagnostics import run_doctor
        rep = asyncio.run(run_doctor())
        console.print(Panel("\n".join(rep.render_lines()), title=f"doctor — {rep.status.value}"))
    elif cmd == "system":
        from buster.diagnostics.system import run_system_check
        _checks(console, [c.model_dump() for c in run_system_check()])
    elif cmd == "network":
        import asyncio

        from buster.diagnostics.network import run_network_check
        _checks(console, [c.model_dump() for c in asyncio.run(run_network_check())])
    elif cmd == "research" and arg:
        try:
            with console.status("Researching…"):
                with httpx.Client(timeout=180.0) as c:
                    r = c.post(f"{config.base_url}/api/research", json={"question": arg}).json()
            console.print(f"[green]✓[/] {r['title']} — {r['sources']} source(s) — id {r['report_id']}")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Error:[/] {exc}")
    elif cmd == "reports":
        _remote_table(console, config, "/reports", "reports", ["id", "title", "version"])
    elif cmd == "nodes":
        from buster.discovery import get_discovery
        for n in get_discovery().list_nodes():
            console.print(f"  {n['name']} [{n['trust']}]")
    elif cmd == "alerts":
        from buster.scheduler import get_alerts
        items = get_alerts().list()
        console.print("[green]No open alerts.[/]" if not items else
                      "\n".join(f"[yellow]![/] {a['title']}" for a in items))
    elif cmd == "workspace":
        console.print(f"Buildly workspace enabled: {config.buildly.workspace_enabled}")
    else:
        console.print(f"[dim]Unknown command: /{cmd} (try /help)[/]")
    return False


def _checks(console: Console, checks: list[dict]) -> None:
    icons = {"ok": "[green]✓[/]", "warning": "[yellow]![/]", "critical": "[red]✕[/]", "unknown": "[dim]?[/]"}
    for c in checks:
        console.print(f"  {icons[c['status']]} {c['check']}: {c['summary']}")


def _remote_table(console: Console, config, path: str, key: str, cols: list[str]) -> None:
    try:
        with httpx.Client(timeout=10.0) as c:
            data = c.get(f"{config.base_url}/api{path}").json()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error:[/] {exc}")
        return
    for item in data.get(key, []):
        console.print("  " + " · ".join(str(item.get(col, "")) for col in cols))
