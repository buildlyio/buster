"""Buster CLI entrypoint (Typer + Rich).

Commands talk to Buster Core over the local API when the service is running, so
the CLI and web share the same conversations, tasks, and reports. Offline
commands (doctor, service control) work without the service.
"""

from __future__ import annotations

import asyncio

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from buster import __version__
from buster.cli import service as svc
from buster.config import load_config

app = typer.Typer(help="Buster — local-first assistant", no_args_is_help=False, add_completion=False)
console = Console()


def _api(path: str, method: str = "GET", json: dict | None = None, timeout: float = 120.0):
    config = load_config()
    url = f"{config.base_url}/api{path}"
    with httpx.Client(timeout=timeout) as c:
        r = c.request(method, url, json=json)
        r.raise_for_status()
        return r.json()


def _service_up() -> bool:
    return svc.status()["api_reachable"]


def _require_service() -> bool:
    if _service_up():
        return True
    console.print("[yellow]Buster service is not running.[/] Start it with [bold]buster start[/].")
    return False


# ----------------------------------------------------------------------------
# service control
# ----------------------------------------------------------------------------

@app.command()
def start():
    """Start the Buster background service and report when it's ready."""
    ok, msg = svc.start()
    s = svc.status()
    if s["api_reachable"]:
        cfg = load_config()
        try:
            from buster.discovery import naming

            host = naming.primary_name()
        except Exception:  # noqa: BLE001
            host = "buster.local"
        console.print(Panel(
            f"[green]✓ Buster is ready.[/]\n"
            f"API:  {cfg.base_url}/api\n"
            f"Web:  http://{host}:{cfg.server.port}  ·  http://localhost:{cfg.server.port}\n"
            f"[dim]buster            open the assistant\n"
            f"buster open       open the web UI\n"
            f"buster guide      getting-started walkthrough[/]",
            title="Started", border_style="green"))
    else:
        console.print(f"[yellow]![/] {msg} "
                      "[dim]API not responding yet — check 'buster logs' / 'buster doctor'.[/]")


@app.command()
def stop():
    """Stop the Buster background service."""
    ok, msg = svc.stop()
    console.print(f"[green]✓[/] {msg}")


@app.command()
def restart():
    """Restart the Buster background service."""
    svc.stop()
    ok, msg = svc.start()
    console.print(f"[green]✓[/] {msg}")


@app.command()
def status():
    """Show service status."""
    s = svc.status()
    table = Table(show_header=False, box=None)
    table.add_row("Running", "[green]yes[/]" if s["running"] else "[red]no[/]")
    table.add_row("PID", str(s["pid"] or "-"))
    table.add_row("API", "[green]reachable[/]" if s["api_reachable"] else "[yellow]unreachable[/]")
    table.add_row("URL", s["url"])
    if s["api_reachable"]:
        st = _api("/status")
        prof = st["capability_profile"]
        model = (st["models"][0]["name"] if st["models"] else "no model")
        table.add_row("Local model", model)
        table.add_row("Policy", st["inference_policy"])
        table.add_row("Recommended class", prof["recommended_model_class"])
        table.add_row("Trusted nodes", str(st["trusted_nodes"]))
    console.print(Panel(table, title="Buster status"))


@app.command()
def logs(lines: int = typer.Option(40, help="Number of log lines")):
    """Show recent service logs."""
    console.print(svc.logs(lines))


@app.command()
def doctor():
    """Inspect Buster itself and print a health report."""
    from buster.diagnostics import run_doctor

    report = asyncio.run(run_doctor())
    color = {"ok": "green", "warning": "yellow", "critical": "red", "unknown": "white"}[report.status.value]
    console.print(Panel("\n".join(report.render_lines()),
                        title=f"buster doctor — [{color}]{report.status.value}[/]"))


@app.command()
def open():
    """Open the local web interface in a browser."""
    import webbrowser

    config = load_config()
    webbrowser.open(config.base_url)
    console.print(f"Opening {config.base_url}")


@app.command()
def guide():
    """Show the getting-started walkthrough."""
    from buster.cli.guide import print_guide

    print_guide(console)


@app.command()
def setup():
    """Detect and choose a model provider (Ollama / LM Studio / remote)."""
    from buster.cli.onboarding import run_provider_onboarding

    run_provider_onboarding(console)


@app.command(name="check-update")
def check_update():
    """Check whether a newer Buster release is available on GitHub."""
    from buster.updates import check_for_update

    info = asyncio.run(check_for_update(force=True))
    if info["latest"] is None:
        console.print("[yellow]Could not reach GitHub to check for updates.[/]")
    elif info["available"]:
        console.print(f"[green]Update available:[/] {info['current']} → [bold]{info['latest']}[/]")
        console.print("Run [bold]buster update[/] to install it.")
    else:
        console.print(f"[green]Buster is up to date[/] ({info['current']}).")


@app.command()
def update(
    yes: bool = typer.Option(False, "--yes", "-y", help="Update without confirmation"),
):
    """Update Buster to the latest release by re-running the installer."""
    import subprocess

    from buster.updates import check_for_update

    info = asyncio.run(check_for_update(force=True))
    if info["latest"] and not info["available"]:
        console.print(f"[green]Already up to date[/] ({info['current']}).")
        if not yes and not typer.confirm("Re-run the installer anyway?", default=False):
            return
    elif info["available"]:
        console.print(f"Update available: {info['current']} → [bold]{info['latest']}[/]")

    if not yes and not typer.confirm("Download and install the update now?", default=True):
        console.print("[dim]Cancelled.[/]")
        return

    console.print("Updating Buster via the installer…")
    # Re-run the official installer, which clones/pulls latest and reinstalls.
    cmd = "curl -fsSL https://install.buster.buildly.io | sh"
    rc = subprocess.run(cmd, shell=True).returncode
    if rc == 0:
        console.print("[green]✓[/] Update complete. Run [bold]buster restart[/] to apply.")
    else:
        console.print("[red]Update failed.[/] Try re-running: " + cmd)


@app.command()
def uninstall(
    purge: bool = typer.Option(False, "--purge", help="Also delete Buster data (irreversible)"),
    keep_program: bool = typer.Option(
        False, "--keep-program", help="Keep ~/.buster/venv and the CLI shim (only remove the service)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Cleanly remove Buster: stop it, unload+remove the user service, and delete
    the installed environment. Data is preserved unless --purge."""
    from buster.config import get_paths

    paths = get_paths()
    console.print("This will:")
    console.print("  • stop Buster and unload its launchd/systemd user service")
    if not keep_program:
        console.print("  • remove ~/.buster/venv and the 'buster' CLI shim")
    console.print(f"  • {'DELETE' if purge else 'preserve'} data at {paths.home}"
                  + ("  [red](irreversible)[/]" if purge else " (use --purge to delete)"))
    if not yes and not typer.confirm("Proceed?", default=False):
        console.print("[dim]Cancelled.[/]")
        return

    for line in svc.remove_service():
        console.print(f"  [green]✓[/] {line}")
    if not keep_program:
        for line in svc.remove_program():
            console.print(f"  [green]✓[/] {line}")

    if purge:
        import shutil

        shutil.rmtree(paths.home, ignore_errors=True)
        console.print(f"  [yellow]✓ Deleted data at {paths.home}[/]")
    else:
        console.print(f"  [dim]Data preserved at {paths.home}[/]")

    console.print("\n[green]Buster uninstalled.[/] Thanks for trying it — buildly.io 🐰")


@app.command()
def serve():
    """Run the Core server in the foreground (used by the service)."""
    import uvicorn

    config = load_config()
    uvicorn.run("buster.api.app:create_app", factory=True,
                host=config.server.host, port=config.server.port, log_level="info")


# ----------------------------------------------------------------------------
# assistant
# ----------------------------------------------------------------------------

@app.command()
def ask(question: str = typer.Argument(..., help="Question for Buster")):
    """Ask Buster a question (uses local-first inference)."""
    if not _require_service():
        return
    with console.status("Thinking…"):
        r = _api("/ask", "POST", {"prompt": question})
    console.print(Markdown(r["content"] or "_(no content)_"))
    console.print(f"[dim]{r['model']} · {r['inference_location']} · "
                  f"data left machine: {'yes' if r['external_data_shared'] else 'no'}"
                  f"{' · tools: ' + ', '.join(r['tools_used']) if r['tools_used'] else ''}[/]")


@app.command()
def research(
    topic: str = typer.Argument(..., help="Research topic"),
    act: bool = typer.Option(False, "--act", help="Offer to launch an agent on the top solution"),
):
    """Research a topic, propose solutions, and (optionally) launch an agent."""
    if not _require_service():
        return
    with console.status("Researching…"):
        r = _api("/research", "POST", {"question": topic})
    console.print(f"[green]✓[/] {r['title']} — {r['sources']} source(s)")
    console.print(f"Report id: [bold]{r['report_id']}[/]  (buster report show {r['report_id']})")

    solutions = r.get("solutions") or []
    if solutions:
        console.print("\n[bold]Proposed solutions[/] "
                      f"[dim]({r.get('solutions_engine', 'deterministic')})[/]")
        for i, s in enumerate(solutions, 1):
            console.print(f"  {i}. [bold]{s['title']}[/]"
                          + (f" — {s['detail']}" if s.get("detail") else ""))

    action = r.get("action")
    if not action:
        return
    console.print(f"\n[bold]Recommended:[/] {action['summary']}")
    if not act:
        console.print("[dim]Launch an agent to do it:  buster research \""
                      f"{topic}\" --act[/]")
        return

    # Propose → one-click (one confirmation) to run. Offer where + when.
    runtimes = action.get("runtime_options") or []
    rec = action.get("recommended_runtime") or (runtimes[0] if runtimes else "")
    console.print(f"\n[bold]Where[/] (runtime): {', '.join(runtimes) or '(none detected)'}")
    runtime_id = typer.prompt("Run with which runtime?", default=rec) if runtimes else ""
    if not runtime_id:
        console.print("[yellow]No runtime available.[/] Try 'buster dev setup' or 'buster runtimes'.")
        return
    when = typer.prompt("When? [now/schedule/queue]", default="now")

    from buster.runtimes import get_runtime_service

    rsvc = get_runtime_service()
    perm_id = None
    if when == "now" and rsvc.is_real(runtime_id):
        console.print(f"[yellow]'{runtime_id}' is a real external runtime (risk 2).[/]")
        if not typer.confirm("Approve running it now?", default=False):
            console.print("[dim]Cancelled.[/]")
            return
        from buster.runtimes import RuntimeTask

        perm = asyncio.run(rsvc.request_submission(runtime_id, RuntimeTask(prompt="act")))
        if perm:
            asyncio.run(get_permissions_decide(perm.id))
            perm_id = perm.id

    with console.status(f"Launching {runtime_id}…"):
        res = _api("/research/act", "POST", {
            "prompt": action["prompt"], "runtime_id": runtime_id,
            "when": when, "permission_id": perm_id})
    if res.get("launched"):
        run = res["run"]
        console.print(f"[green]✓[/] {run['outcome']} — run {run['id']}")
        if run.get("output"):
            console.print(Panel(run["output"][:1500], title="Agent output (data only)"))
    else:
        console.print(f"[yellow]{res.get('note', 'Not launched.')}[/]")


@app.command()
def reports():
    """List saved reports."""
    if not _require_service():
        return
    data = _api("/reports")
    table = Table(title="Reports")
    table.add_column("ID"); table.add_column("Title"); table.add_column("Updated"); table.add_column("v")
    for r in data["reports"]:
        table.add_row(r["id"], r["title"], (r["updated_at"] or "").replace("T", " "), str(r["version"]))
    console.print(table)


report_app = typer.Typer(help="Report commands")
app.add_typer(report_app, name="report")


@report_app.command("show")
def report_show(report_id: str):
    """Show a report as Markdown."""
    if not _require_service():
        return
    r = _api(f"/reports/{report_id}")
    console.print(Markdown(r["markdown"]))


# ----------------------------------------------------------------------------
# diagnostics
# ----------------------------------------------------------------------------

system_app = typer.Typer(help="System diagnostics")
app.add_typer(system_app, name="system")


@system_app.command("check")
def system_check():
    """Run a system health check."""
    from buster.diagnostics.system import run_system_check

    _print_checks([c.model_dump() for c in run_system_check()])


@system_app.command("status")
def system_status():
    """Show the hardware capability profile."""
    from buster.models.capability import detect_capabilities

    console.print(Panel(detect_capabilities().explain(), title="Capability profile"))


network_app = typer.Typer(help="Network diagnostics")
app.add_typer(network_app, name="network")


@network_app.command("check")
def network_check():
    """Run a network health check."""
    from buster.diagnostics.network import run_network_check

    _print_checks([c.model_dump() for c in asyncio.run(run_network_check())])


@network_app.command("discover")
def network_discover():
    """Probe configured service URLs and list discovered nodes/services."""
    from buster.discovery import get_discovery

    disco = get_discovery()
    for url in load_config().discovery.service_urls:
        asyncio.run(disco.probe_url(url))
    _print_nodes_services(disco.list_nodes(), disco.list_services())


def _print_checks(checks: list[dict]):
    icons = {"ok": "[green]✓[/]", "warning": "[yellow]![/]", "critical": "[red]✕[/]", "unknown": "[dim]?[/]"}
    for c in checks:
        console.print(f"{icons[c['status']]} [bold]{c['check']}[/]: {c['summary']}")
        for rec in c.get("recommendations", []):
            console.print(f"    [dim]→ {rec}[/]")


# ----------------------------------------------------------------------------
# alerts / memory / tools / skills / nodes / services / prompts
# ----------------------------------------------------------------------------

@app.command()
def alerts():
    """List open alerts."""
    from buster.scheduler import get_alerts

    items = get_alerts().list()
    if not items:
        console.print("[green]No open alerts.[/]")
        return
    for a in items:
        console.print(f"[yellow]![/] [bold]{a['title']}[/] — {a['detail']}")


memory_app = typer.Typer(help="Memory commands")
app.add_typer(memory_app, name="memory")


@memory_app.command("search")
def memory_search(query: str):
    """Search indexed Markdown memory (FTS5)."""
    from buster.memory import get_memory

    hits = get_memory().search(query)
    if not hits:
        console.print("[dim]No matches.[/]")
        return
    for h in hits:
        console.print(Panel(h.text, title=h.heading_path or h.path))


@app.command()
def tools():
    """List available tools."""
    from buster.tools import get_registry

    table = Table(title="Tools")
    table.add_column("ID"); table.add_column("Pack"); table.add_column("Risk"); table.add_column("Description")
    for t in get_registry().all():
        table.add_row(t.id, t.pack, str(t.risk_level), t.description)
    console.print(table)


@app.command()
def skills():
    """List available skills."""
    from buster.skills import get_skill_registry

    table = Table(title="Skills")
    table.add_column("ID"); table.add_column("Name"); table.add_column("Description")
    for s in get_skill_registry().all():
        table.add_row(s.id, s.name, s.description)
    console.print(table)


@app.command()
def nodes():
    """List discovered Buster nodes."""
    from buster.discovery import get_discovery

    _print_nodes_services(get_discovery().list_nodes(), [])


@app.command()
def services():
    """List discovered LCDP services."""
    from buster.discovery import get_discovery

    _print_nodes_services([], get_discovery().list_services())


def _print_nodes_services(nodes: list[dict], services: list[dict]):
    if nodes:
        table = Table(title="Buster nodes")
        table.add_column("Name"); table.add_column("Trust"); table.add_column("API")
        for n in nodes:
            table.add_row(n["name"], n["trust"], n["api_url"])
        console.print(table)
    if services:
        table = Table(title="Services")
        table.add_column("Name"); table.add_column("Product"); table.add_column("Trust")
        for s in services:
            table.add_row(s["name"], s["product"], s["trust"])
        console.print(table)
    if not nodes and not services:
        console.print("[dim]Nothing discovered. Configure service URLs in config, or run 'buster network discover'.[/]")


runtimes_app = typer.Typer(help="Agent runtimes (Buster, Hermes, OpenClaw, ...)")
app.add_typer(runtimes_app, name="runtimes")


@runtimes_app.callback(invoke_without_command=True)
def runtimes_main(ctx: typer.Context):
    """List detected agent runtimes (default)."""
    if ctx.invoked_subcommand is not None:
        return
    from buster.runtimes import detect_runtimes

    infos = asyncio.run(detect_runtimes())
    table = Table(title="Agent runtimes")
    table.add_column("ID"); table.add_column("Name"); table.add_column("Type")
    table.add_column("Status"); table.add_column("Via"); table.add_column("Tasks")
    for r in infos:
        table.add_row(r.id, r.name, r.runtime_type, r.status.value, r.detected_via,
                      "on" if r.task_submission_enabled else "off")
    console.print(table)


@runtimes_app.command("submit")
def runtimes_submit(
    runtime_id: str,
    prompt: str,
    timeout: int = typer.Option(120, help="Task timeout in seconds"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve submission to a real runtime"),
):
    """Submit a bounded task to a runtime. Real runtimes require approval.

    A delegated result is DATA ONLY — it never triggers a Buster action.
    """
    from buster.runtimes import RuntimeSubmissionError, RuntimeTask, get_runtime_service

    svc = get_runtime_service()
    task = RuntimeTask(prompt=prompt, timeout_s=timeout)

    if svc.is_real(runtime_id):
        console.print(f"[yellow]'{runtime_id}' is a real external runtime.[/] "
                      "Submitting sends this task to it (risk level 2).")
        if not yes and not typer.confirm("Approve submission?", default=False):
            console.print("[dim]Cancelled.[/]")
            return
        # Record an approved permission for the audit trail.
        perm = asyncio.run(svc.request_submission(runtime_id, task))
        if perm:
            asyncio.run(get_permissions_decide(perm.id))

    try:
        run = asyncio.run(svc.submit(runtime_id, task))
    except RuntimeSubmissionError as exc:
        console.print(f"[red]Blocked:[/] {exc}")
        return
    console.print(Panel(run.output or run.error or "(no output)",
                        title=f"{run.executing_runtime} · {run.status.value}"))
    console.print(f"[dim]run {run.run_id} · {run.inference_location} · "
                  f"data left machine: {'yes' if run.external_data_shared else 'no'}[/]")


@runtimes_app.command("runs")
def runtimes_runs(runtime_id: str = typer.Option(None, help="Filter by runtime id")):
    """List recent delegated runs."""
    from buster.runtimes import get_runtime_service

    runs = get_runtime_service().list_runs(runtime_id)
    if not runs:
        console.print("[dim]No runs yet.[/]")
        return
    table = Table(title="Runtime runs")
    table.add_column("Run"); table.add_column("Runtime"); table.add_column("Status")
    table.add_column("When")
    for r in runs:
        table.add_row(r["run_id"], r["runtime_id"], r["status"],
                      (r["created_at"] or "").replace("T", " "))
    console.print(table)


async def get_permissions_decide(permission_id: str) -> None:
    from buster.permissions import get_permissions

    await get_permissions().decide(permission_id, approved=True, decided_by="cli")


# ----------------------------------------------------------------------------
# Buildly dev workflow (P2.2 Phase 1)
# ----------------------------------------------------------------------------

import os as _os  # noqa: E402


def _dev_svc():
    from buster.buildly.devservice_mock import get_dev_service

    return get_dev_service()


@app.command()
def adopt(
    path: str = typer.Argument(".", help="Repository path"),
    review: bool = typer.Option(False, "--review", help="Show the last adoption report"),
):
    """Run a non-destructive adoption scan (or --review the last one).

    The scan is observation-only: it never modifies your application files. It
    writes drafts under .buildly/adoption/ and devdocs/generated/.
    """
    path = _os.path.abspath(_os.path.expanduser(path))
    svc = _dev_svc()
    if review:
        report = asyncio.run(svc.get_adoption_report(path))
        if not report:
            console.print("[yellow]No adoption report yet.[/] Run [bold]buster adopt[/] first.")
            return
    else:
        with console.status("Scanning (observation-only)…"):
            report = asyncio.run(svc.scan_repository(path))
        console.print(f"[green]✓[/] Scan complete [dim](engine: {report.engine}; "
                      "no application files modified)[/]")
        console.print(f"[dim]Wrote: {', '.join(report.output_dirs)}[/]")

    inv = report.inventory
    table = Table(title="Inventory")
    table.add_column("Category"); table.add_column("Count")
    for label, vals in [("frameworks", inv.frameworks), ("languages", inv.languages),
                        ("api routes", inv.api_routes), ("models", inv.models_schemas),
                        ("tests", inv.tests), ("migrations", inv.migrations),
                        ("docs", inv.existing_docs), ("build/deploy", inv.build_deploy)]:
        table.add_row(label, str(len(vals)) if not isinstance(vals, list) or len(vals) != 1
                      else vals[0] if label in ("frameworks", "languages") else str(len(vals)))
    console.print(table)

    if report.proposed_features:
        console.print("\n[bold]Proposed features[/] [dim](inferred — not approved)[/]")
        for f in report.proposed_features:
            console.print(f"  • {f.name} — {f.description} [{f.status.value}]")
    console.print("\n[bold]Statements[/]")
    for s in report.statements:
        color = {"observed": "green", "inferred": "yellow", "unresolved": "dim",
                 "contradictory": "red", "approved": "cyan"}.get(s.status.value, "white")
        console.print(f"  [{color}]{s.status.value}[/] · {s.confidence.value} — {s.text}")
    console.print("\n[dim]Review/approve in the web UI (Adoption Report) — inferred items "
                  "never become product truth automatically.[/]")


buildly_app = typer.Typer(help="Buildly product/repository binding")
app.add_typer(buildly_app, name="buildly")


@buildly_app.command("status")
def buildly_status(path: str = typer.Argument(".", help="Repository path")):
    """Show repository + Buildly binding + offline/sync status."""
    path = _os.path.abspath(_os.path.expanduser(path))
    svc = _dev_svc()
    ctx = asyncio.run(svc.inspect_repository(path))
    binding = asyncio.run(svc.get_binding(path))
    sync = asyncio.run(svc.get_sync_status(path))

    t = Table(show_header=False, box=None)
    t.add_row("Path", ctx.path)
    t.add_row("Git", "yes" if ctx.is_git else "no")
    t.add_row("Branch", ctx.current_branch or "-")
    t.add_row("Framework", ctx.framework or "(unknown)")
    t.add_row("Languages", ", ".join(ctx.languages) or "-")
    t.add_row("Topology", ctx.topology)
    t.add_row("Buildly binding", f"[green]{binding.product_name}[/]" if binding.bound
              else "[yellow]local only[/]")
    t.add_row("Labs", "[green]connected[/]" if sync.connected else "[yellow]offline[/] "
              "[dim](local features still work)[/]")
    if sync.pending:
        t.add_row("Pending sync events", str(sync.pending))
    console.print(Panel(t, title="Buildly status"))


@buildly_app.command("connect")
def buildly_connect(product_id: str, path: str = typer.Argument(".", help="Repository path")):
    """Bind this repository to a Buildly product (writes .buildly/project.yaml)."""
    path = _os.path.abspath(_os.path.expanduser(path))
    binding = asyncio.run(_dev_svc().connect_product(path, product_id))
    console.print(f"[green]✓[/] Bound to {binding.product_name} ({binding.product_id}).")


# ----------------------------------------------------------------------------
# Labs (via bb-agent-manager MCP)
# ----------------------------------------------------------------------------

labs_app = typer.Typer(help="Buildly Labs (via the bb-agent-manager MCP server)")
app.add_typer(labs_app, name="labs")


def _mcp():
    from buster.buildly.mcp_client import get_mcp_client

    return get_mcp_client()


@labs_app.command("status")
def labs_status():
    """Show the bb-agent-manager connection and real Labs auth state."""
    from buster.buildly.mcp_client import LabsAuthState

    client = _mcp()
    if not client.available:
        console.print("[yellow]No bb-agent-manager configured.[/] Set a hosted endpoint "
                      "with [bold]buster labs connect <url>[/] (e.g. http://bespin.home:8000/sse), "
                      "or install the local 'buildly-mcp'.")
        return
    t = Table(show_header=False, box=None)
    t.add_row("MCP transport", client.target.transport.value)
    t.add_row("MCP target", client.target.detail)
    with console.status("Checking Labs auth…"):
        state = asyncio.run(client.auth_state())
    label = {
        LabsAuthState.OK: "[green]connected & authenticated[/]",
        LabsAuthState.UNAUTHENTICATED: "[yellow]not logged in[/] — run 'buster labs login'",
        LabsAuthState.TOKEN_INVALID: "[red]token invalid/expired[/] — run 'buster labs login'",
        LabsAuthState.UNREACHABLE: "[red]MCP server unreachable[/]",
    }[state]
    t.add_row("Labs auth", label)
    console.print(Panel(t, title="Buildly Labs"))


@labs_app.command("connect")
def labs_connect(url: str = typer.Argument(..., help="Hosted MCP SSE URL, e.g. http://bespin.home:8000/sse")):
    """Point Buster at a hosted bb-agent-manager MCP server."""
    from buster.config import load_config, save_config

    cfg = load_config()
    cfg.buildly.mcp_url = url
    cfg.buildly.workspace_enabled = True
    cfg.buildly.mode = "hosted_mcp"
    save_config(cfg)
    console.print(f"[green]✓[/] bb-agent-manager set to {url}. Try [bold]buster labs status[/].")


@labs_app.command("login")
def labs_login(
    token: str = typer.Option("", "--token", help="Manual API token (else OAuth browser flow)"),
):
    """Log in to Labs via bb-agent-manager (OAuth URL, or a manual token)."""
    client = _mcp()
    if not client.available:
        console.print("[yellow]No bb-agent-manager configured.[/] Run 'buster labs connect <url>' first.")
        return
    res = asyncio.run(client.login(token or None))
    # OAuth path returns a URL to open; manual-token path confirms storage.
    url = res.get("authorize_url") if isinstance(res, dict) else None
    if url:
        console.print(f"Open this URL to authorize, then re-run [bold]buster labs status[/]:\n  {url}")
    else:
        console.print(f"[green]✓[/] {res.get('message', res)}")


@labs_app.command("products")
def labs_products():
    """List your Buildly Labs products."""
    client = _mcp()
    if not client.available:
        console.print("[yellow]No bb-agent-manager configured.[/]")
        return
    try:
        products = asyncio.run(client.products())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error:[/] {exc}")
        return
    if not products:
        console.print("[dim]No products (or not authenticated — 'buster labs status').[/]")
        return
    table = Table(title="Labs products")
    table.add_column("ID"); table.add_column("Name")
    for p in products:
        table.add_row(str(p.get("id") or p.get("uuid") or "?"), str(p.get("name") or ""))
    console.print(table)


@labs_app.command("issues")
def labs_issues(
    product_id: str = typer.Option("", "--product", help="Filter by product id"),
    status: str = typer.Option("", "--status", help="Filter by status"),
):
    """List Labs issues (optionally filtered by product/status)."""
    client = _mcp()
    if not client.available:
        console.print("[yellow]No bb-agent-manager configured.[/]")
        return
    try:
        issues = asyncio.run(client.issues(product_id or None, status or None))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error:[/] {exc}")
        return
    if not issues:
        console.print("[dim]No issues found.[/]")
        return
    table = Table(title="Labs issues")
    table.add_column("ID"); table.add_column("Name"); table.add_column("Status")
    for i in issues:
        table.add_row(str(i.get("id") or i.get("uuid") or "?"),
                      str(i.get("name") or i.get("title") or ""), str(i.get("status") or ""))
    console.print(table)


@labs_app.command("associate")
def labs_associate(path: str = typer.Argument(".", help="Repository path")):
    """Suggest a Labs product for this repo and bind it (with confirmation).

    Nothing is written to Labs or .buildly/project.yaml without your explicit yes.
    """
    from buster.buildly.associate import suggest_matches, write_binding

    client = _mcp()
    if not client.available:
        console.print("[yellow]No bb-agent-manager configured.[/] Run 'buster labs connect <url>' first.")
        return
    repo = _os.path.abspath(_os.path.expanduser(path))
    try:
        products = asyncio.run(client.products())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error:[/] {exc}")
        return

    matches = suggest_matches(repo, products)
    console.print(f"Repository: [bold]{_os.path.basename(repo)}[/]")
    if matches:
        table = Table(title="Suggested Labs products")
        table.add_column("#"); table.add_column("Product"); table.add_column("Why")
        for idx, m in enumerate(matches, 1):
            table.add_row(str(idx), m.product_name, m.reason)
        console.print(table)
        console.print("Choose a number to bind, [bold]n[/] to create a new Labs product, "
                      "or [bold]s[/] to skip.")
        choice = typer.prompt("Choose", default="1" if matches else "s")
    else:
        console.print("[yellow]No products to match against.[/]")
        choice = typer.prompt("Create a [n]ew Labs product or [s]kip?", default="n")

    if choice.lower() == "s":
        console.print("[dim]Skipped. No changes made.[/]")
        return
    if choice.lower() == "n":
        name = typer.prompt("New product name", default=_os.path.basename(repo))
        if not typer.confirm(f"Create Labs product '{name}' and bind this repo?", default=True):
            console.print("[dim]Cancelled.[/]")
            return
        try:
            res = asyncio.run(client.create_product(name))
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Create failed:[/] {exc}")
            return
        data = res.get("data", res) if isinstance(res, dict) else {}
        pid = str(data.get("id") or data.get("uuid") or "")
        if not pid:
            console.print(f"[yellow]Product create returned no id (create tools may not be "
                          f"deployed on this server yet): {res}[/]")
            return
        write_binding(repo, pid, name)
        console.print(f"[green]✓[/] Created and bound to {name} ({pid}).")
        return
    try:
        m = matches[int(choice) - 1]
    except (ValueError, IndexError):
        console.print("[red]Invalid choice.[/]")
        return
    if not typer.confirm(f"Bind this repo to '{m.product_name}'?", default=True):
        console.print("[dim]Cancelled.[/]")
        return
    write_binding(repo, m.product_id, m.product_name)
    console.print(f"[green]✓[/] Bound to {m.product_name} ({m.product_id}). "
                  "Wrote .buildly/project.yaml.")


@app.command()
def docs(path: str = typer.Argument(".", help="Repository path")):
    """Generate product documentation + architecture diagrams (drafts)."""
    path = _os.path.abspath(_os.path.expanduser(path))
    svc = _dev_svc()
    d = asyncio.run(svc.generate_documentation(path))
    g = asyncio.run(svc.generate_diagrams(path))
    console.print(f"[green]✓[/] Docs: {', '.join(d)}")
    console.print(f"[green]✓[/] Diagrams: {', '.join(g)}")
    console.print(f"[dim]engine: {svc.engine}[/]")


@app.command()
def scaffold(
    module_name: str = typer.Argument(..., help="Module/service name, e.g. 'Inventory Service'"),
    models: str = typer.Option("", "--models", "-m", help="Comma-separated model names"),
    out: str = typer.Option("", "--out", "-o", help="Output directory (default: ./<slug>)"),
    no_docker: bool = typer.Option(False, "--no-docker", help="Skip the Dockerfile"),
    force: bool = typer.Option(False, "--force", help="Write into a non-empty directory"),
):
    """Scaffold a runnable FastAPI + SQLAlchemy Buildly module with CRUD routes."""
    import re

    from buster.scaffold import ScaffoldPlan, scaffold_fastapi_module

    model_list = [m.strip() for m in models.split(",") if m.strip()]
    slug = re.sub(r"[^a-z0-9]+", "-", module_name.lower()).strip("-") or "module"
    out_dir = _os.path.abspath(_os.path.expanduser(out or f"./{slug}"))
    plan = ScaffoldPlan(module_name=module_name, models=model_list,
                        output_dir=out_dir, include_docker=not no_docker)
    try:
        res = scaffold_fastapi_module(plan, force=force)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/]")
        return
    console.print(Panel(
        f"[green]✓ Scaffolded {module_name}[/]\n"
        f"Location: {res.output_dir}\n"
        f"Models: {', '.join(res.models)}\n"
        f"Files: {', '.join(res.files_written)}\n\n"
        f"[dim]Run:[/] cd {res.output_dir} && pip install -r requirements.txt && sh run.sh\n"
        f"[dim]Then open http://localhost:8000/docs[/]",
        title="Buildly module"))


# ----------------------------------------------------------------------------
# Phase 2: approve → contracts → sync
# ----------------------------------------------------------------------------

@app.command()
def approve(
    statement_id: str = typer.Argument(..., help="Statement id from 'buster adopt'"),
    path: str = typer.Option(".", "--path", help="Repository path"),
    edit: str = typer.Option("", "--edit", help="Edit the text before approving"),
    reject: bool = typer.Option(False, "--reject", help="Reject instead of approve"),
    deprecate: bool = typer.Option(False, "--deprecate", help="Mark deprecated"),
):
    """Approve (or reject/deprecate) an inferred statement into a local contract.

    Approving queues a sync event; nothing reaches Labs until 'buster sync'.
    Inferred items never become product truth automatically.
    """
    repo = _os.path.abspath(_os.path.expanduser(path))
    svc = _dev_svc()
    if reject or deprecate:
        status = "rejected" if reject else "deprecated"
        asyncio.run(svc.set_statement_status(repo, statement_id, status))
        console.print(f"[yellow]Marked {statement_id} {status}[/] (local only, no sync).")
        return
    res = asyncio.run(svc.approve_statement(repo, statement_id, text=edit or None))
    c = res["contract"]
    console.print(f"[green]✓[/] Approved → contract {c['id']}"
                  + (" [dim](edited)[/]" if c.get("edited") else ""))
    console.print(f"[dim]Queued sync event {res['sync_event']}. Run 'buster sync' to push.[/]")


@app.command()
def contracts(path: str = typer.Argument(".", help="Repository path")):
    """List locally-approved contracts for this repo."""
    repo = _os.path.abspath(_os.path.expanduser(path))
    items = asyncio.run(_dev_svc().list_contracts(repo))
    if not items:
        console.print("[dim]No contracts yet. Approve items with 'buster approve <id>'.[/]")
        return
    table = Table(title="Local contracts")
    table.add_column("ID"); table.add_column("Kind"); table.add_column("Status")
    table.add_column("Synced"); table.add_column("Text")
    for c in items:
        table.add_row(c["id"], c["kind"], c["status"],
                      "yes" if c["labs_synced"] else "no", c["text"][:50])
    console.print(table)


sync_app = typer.Typer(help="Synchronization with Buildly Labs")
app.add_typer(sync_app, name="sync")


@sync_app.callback(invoke_without_command=True)
def sync_main(ctx: typer.Context, path: str = typer.Option(".", "--path")):
    """Push pending sync events to Labs (default). Offline-safe."""
    if ctx.invoked_subcommand is not None:
        return
    repo = _os.path.abspath(_os.path.expanduser(path))
    with console.status("Syncing…"):
        res = asyncio.run(_dev_svc().sync_push(repo))
    if not res.get("pushed"):
        console.print(f"[yellow]Not pushed:[/] {res.get('reason')}. "
                      "[dim]Local work is safe; pending events kept for retry.[/]")
    else:
        r = res["result"]
        console.print(f"[green]✓[/] applied {r['applied']}, conflicts {r['conflicts']}, "
                      f"failed {r['failed']} (of {r['processed']}).")
    _print_sync_status(res["status"])


@sync_app.command("status")
def sync_status(path: str = typer.Argument(".", help="Repository path")):
    """Show pending/applied/conflict/failed sync counts + Labs connection."""
    repo = _os.path.abspath(_os.path.expanduser(path))
    status = asyncio.run(_dev_svc().get_sync_status(repo)).model_dump()
    # Add live Labs connection state.
    from buster.buildly.mcp_client import get_mcp_client

    client = get_mcp_client()
    if client.available:
        state = asyncio.run(client.auth_state())
        status["connected"] = state.value == "ok"
        status["labs_state"] = state.value
    _print_sync_status(status)


def _print_sync_status(status: dict):
    t = Table(show_header=False, box=None)
    labs = status.get("labs_state", "connected" if status.get("connected") else "offline")
    t.add_row("Labs", "[green]connected[/]" if status.get("connected")
              else f"[yellow]{labs}[/] [dim](local work continues)[/]")
    t.add_row("Pending", str(status.get("pending", 0)))
    t.add_row("Applied", str(status.get("applied", 0)))
    t.add_row("Conflicts", f"[red]{status.get('conflicts', 0)}[/]" if status.get("conflicts")
              else "0")
    t.add_row("Failed", str(status.get("failed", 0)))
    console.print(Panel(t, title="Sync status"))


# ----------------------------------------------------------------------------
# Developer setup: bb-code + tokenjam (P2.3)
# ----------------------------------------------------------------------------

dev_app = typer.Typer(help="Developer tooling (bb-code, TokenJam)")
app.add_typer(dev_app, name="dev")


@dev_app.callback(invoke_without_command=True)
def dev_main(ctx: typer.Context):
    """Show developer-tool status (default)."""
    if ctx.invoked_subcommand is not None:
        return
    from buster.dev import dev_status

    table = Table(title="Developer tools")
    table.add_column("Tool"); table.add_column("Present"); table.add_column("Detail")
    for t in dev_status():
        detail = t.version or (t.install_cmd and "[dim]install: " + t.install_cmd + "[/]") or t.note
        table.add_row(t.name, "[green]yes[/]" if t.present else "[yellow]no[/]", detail[:70])
    console.print(table)


@dev_app.command("setup")
def dev_setup():
    """Detect dev tools; register bb-code as a runtime; guide optional installs.

    Buster never installs packages silently — it shows the exact command and
    asks. TokenJam is read-only (Buster sends it nothing).
    """
    from buster.dev import dev_status
    from buster.dev.setup import register_bb_code_runtime

    statuses = {t.key: t for t in dev_status()}

    # bb-code → register as a CLI runtime if present.
    if statuses["bb_code"].present:
        register_bb_code_runtime()
        console.print("[green]✓[/] bb-code detected and registered as a runtime "
                      "([bold]buster runtimes[/]).")
    else:
        console.print("[yellow]bb-code not found.[/] Local-first codegen (optional). Install with:")
        console.print(f"  [bold]{statuses['bb_code'].install_cmd}[/]")
        if typer.confirm("Show the install steps and continue?", default=False):
            console.print("[dim]Run the command above yourself; Buster won't install it for you.[/]")

    # tokenjam
    tj = statuses["tokenjam"]
    if tj.present:
        console.print("[green]✓[/] TokenJam detected — 'buster dev tokens' for a read-only report.")
    else:
        console.print("[yellow]TokenJam not found.[/] Token-efficiency telemetry (optional). Install with:")
        console.print(f"  [bold]{tj.install_cmd}[/]")
    console.print(f"[dim]{__import__('buster.dev.setup', fromlist=['TOKENJAM_CREDIT']).TOKENJAM_CREDIT}[/]")

    # Offer developer profile if this looks like a dev machine.
    from buster.buildly.devtools import detect_dev_tools, should_offer_developer_profile

    if should_offer_developer_profile(detect_dev_tools()):
        from buster.personality import get_personality

        if get_personality().current_profile() != "developer" and typer.confirm(
            "Enable Buster's developer profile?", default=True
        ):
            get_personality().set_profile("developer", reason="dev setup")
            console.print("[green]✓[/] Developer profile enabled.")


@dev_app.command("tokens")
def dev_tokens():
    """Show TokenJam's local token-efficiency findings (read-only)."""
    from buster.dev import tokenjam_summary

    s = tokenjam_summary()
    if not s.available:
        console.print(f"[yellow]{s.note}[/]")
        return
    if s.findings:
        table = Table(title="TokenJam findings")
        table.add_column("#"); table.add_column("Finding")
        for i, f in enumerate(s.findings[:20], 1):
            text = f.get("title") or f.get("message") or f.get("recommendation") or str(f)
            table.add_row(str(i), str(text)[:80])
        console.print(table)
    elif s.raw:
        console.print(s.raw)
    else:
        console.print(f"[dim]{s.note}[/]")
    console.print(f"[dim]{s.credit}[/]")


# ----------------------------------------------------------------------------
# Dev workflow Phase 3: work → context → agent run → review
# ----------------------------------------------------------------------------

@app.command()
def work(
    issue: str = typer.Argument(..., help="Labs issue id, or a local issue title"),
    path: str = typer.Option(".", "--path", help="Repository path"),
    local: bool = typer.Option(False, "--local", help="Treat <issue> as a local issue title"),
    run: str = typer.Option("", "--run", help="Run an agent (runtime id) on the context package"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve real-runtime submission"),
):
    """Start work on an issue: build a bounded context package, optionally run an agent.

    The context package excludes secrets. Real external runtimes require approval;
    agent results are data-only and never auto-trigger changes.
    """
    repo = _os.path.abspath(_os.path.expanduser(path))
    svc = _dev_svc()

    if local:
        issue_dict = {"id": issue.lower().replace(" ", "-"), "title": issue, "source": "local"}
    else:
        issue_dict = {"id": issue, "title": issue, "source": "labs"}

    res = asyncio.run(svc.start_work(repo, issue_dict))
    pkg = res["context_package"]
    console.print(Panel(
        f"[bold]{res['issue']['title']}[/] ({res['issue']['id']})\n"
        f"Context package: {pkg['id']}\n"
        f"Files: {len(pkg['included_files'])} · ~{pkg['token_estimate']} tokens\n"
        f"[dim]{pkg['excluded_note']}[/]",
        title="Start Work"))
    for f in pkg["included_files"][:15]:
        console.print(f"  • {f}")

    if not run:
        console.print("\n[dim]Run an agent with:  buster work "
                      f"{issue} --run <runtime-id>  (see 'buster runtimes')[/]")
        return

    from buster.runtimes import get_runtime_service

    rsvc = get_runtime_service()
    perm_id = None
    if rsvc.is_real(run):
        console.print(f"[yellow]'{run}' is a real external runtime[/] (risk level 2).")
        if not yes and not typer.confirm("Approve running it on this context?", default=False):
            console.print("[dim]Cancelled.[/]")
            return
        from buster.runtimes import RuntimeTask

        perm = asyncio.run(rsvc.request_submission(run, RuntimeTask(prompt="work")))
        if perm:
            asyncio.run(get_permissions_decide(perm.id))
            perm_id = perm.id

    with console.status(f"Running {run}…"):
        out = asyncio.run(svc.run_agent(repo, pkg["id"], run, permission_id=perm_id))
    if "error" in out:
        console.print(f"[red]{out['error']}[/]")
        return
    r = out["run"]
    console.print(f"[green]✓[/] run {r['id']} — {r['outcome']}")
    if out.get("output"):
        console.print(Panel(out["output"][:1500], title="Agent output (data only)"))
    console.print(f"[dim]Review with:  buster review {r['id']} --path {path}[/]")


@app.command()
def review(
    run_id: str = typer.Argument(..., help="Agent run id from 'buster work'"),
    path: str = typer.Option(".", "--path", help="Repository path"),
):
    """Review the change manifest for an agent run. Never auto-merges."""
    repo = _os.path.abspath(_os.path.expanduser(path))
    res = asyncio.run(_dev_svc().review_changes(repo, run_id))
    m = res["manifest"]
    console.print(Panel(
        f"Run: {m['run_id']}\n"
        f"Changed files: {len(m['changed_files'])}\n"
        f"Tests: {', '.join(t['check'] + ('✓' if t['passed'] else '✕') for t in m['tests']) or '—'}\n"
        f"Unresolved: {'; '.join(m['unresolved_questions']) or 'none'}",
        title="Change review"))
    console.print(f"[yellow]{res['note']}[/]")


forge_app = typer.Typer(help="Buildly Forge marketplace apps")
app.add_typer(forge_app, name="forge")


@forge_app.command("new")
def forge_new(
    name: str = typer.Argument(..., help="App name"),
    description: str = typer.Option("", "--description", "-d"),
    category: str = typer.Option("starter", "--category", "-c"),
    out: str = typer.Option("", "--out", "-o", help="Output dir (default: ./<slug>)"),
):
    """Create a new Buildly Forge app skeleton (marketplace structure + manifest)."""
    import re

    from buster.scaffold import new_forge_app

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "app"
    out_dir = _os.path.abspath(_os.path.expanduser(out or f"./{slug}"))
    try:
        res = new_forge_app(out_dir, name, description, category)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/]")
        return
    console.print(Panel(
        f"[green]✓ Created Forge app '{name}'[/]\n"
        f"Location: {res.output_dir}\n"
        f"Files: {', '.join(res.files_written)}\n\n"
        f"[dim]Next:[/] fill in BUILDLY.yaml, add screenshots, "
        f"then 'buster scaffold' a service if you need one.",
        title="Forge app"))


@forge_app.command("adapt")
def forge_adapt(
    path: str = typer.Argument(".", help="Existing repository path"),
    name: str = typer.Option("", "--name", "-n", help="App name (default: folder name)"),
    description: str = typer.Option("", "--description", "-d"),
    category: str = typer.Option("starter", "--category", "-c"),
):
    """Add Forge/marketplace structure to an EXISTING repo (additive; never
    modifies application code)."""
    from buster.scaffold import adapt_to_marketplace

    root = _os.path.abspath(_os.path.expanduser(path))
    res = adapt_to_marketplace(root, name or _os.path.basename(root), description, category)
    console.print(f"[green]✓[/] Added: {', '.join(res.files_written) or '(nothing — all present)'}")
    if res.files_skipped:
        console.print(f"[dim]Left untouched (already present): {', '.join(res.files_skipped)}[/]")
    console.print("[dim]No application files were modified. Fill in BUILDLY.yaml to finish.[/]")


prompts_app = typer.Typer(help="Prompt library")
app.add_typer(prompts_app, name="prompts")


@prompts_app.callback(invoke_without_command=True)
def prompts_main(ctx: typer.Context):
    """List prompt records (default)."""
    if ctx.invoked_subcommand is not None:
        return
    from buster.prompts import get_prompts

    table = Table(title="Prompt library")
    table.add_column("ID"); table.add_column("Title"); table.add_column("Visibility")
    for p in get_prompts().list():
        table.add_row(p.id, p.title, p.visibility)
    console.print(table)


@prompts_app.command("save")
def prompts_save(title: str, prompt: str = typer.Option("", help="Original prompt text")):
    """Save a prompt record."""
    from buster.prompts import get_prompts
    from buster.prompts.service import PromptRecord

    rec = get_prompts().save(PromptRecord(id="", title=title, original_prompt=prompt))
    console.print(f"[green]✓[/] saved {rec.id}")


@prompts_app.command("search")
def prompts_search(query: str):
    """Search prompt records."""
    from buster.prompts import get_prompts

    for p in get_prompts().search(query):
        console.print(f"[bold]{p.id}[/] {p.title}")


@prompts_app.command("show")
def prompts_show(prompt_id: str):
    """Show a prompt record."""
    from buster.prompts import get_prompts

    rec = get_prompts().get(prompt_id)
    if not rec:
        console.print("[red]Not found.[/]")
        return
    console.print(Markdown(rec.to_markdown()))


@app.command()
def workspace():
    """Show Buildly Workspace status."""
    config = load_config()
    b = config.buildly
    console.print(Panel(
        f"Enabled: {b.workspace_enabled}\nMode: {b.mode}\nMCP URL: {b.mcp_url or '-'}",
        title="Buildly Workspace"))


@app.command()
def config():
    """Show current configuration."""
    import json

    console.print_json(json.dumps(load_config().model_dump()))


# ----------------------------------------------------------------------------
# interactive mode (default when no command given)
# ----------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, version: bool = typer.Option(False, "--version")):
    if version:
        console.print(f"Buster {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        from buster.cli.interactive import run_interactive

        run_interactive(console)


if __name__ == "__main__":
    app()
