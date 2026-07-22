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
    """Start the Buster background service."""
    ok, msg = svc.start()
    console.print(f"[green]✓[/] {msg}" if ok else f"[red]✕[/] {msg}")


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
def research(topic: str = typer.Argument(..., help="Research topic")):
    """Run a web research task and save a local report."""
    if not _require_service():
        return
    with console.status("Researching…"):
        r = _api("/research", "POST", {"question": topic})
    console.print(f"[green]✓[/] {r['title']} — {r['sources']} source(s)")
    console.print(f"Report id: [bold]{r['report_id']}[/]  (buster report show {r['report_id']})")


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
