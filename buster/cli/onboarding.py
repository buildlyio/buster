"""Interactive provider onboarding.

Detects local + LAN inference providers (Ollama, LM Studio) and lets the user
pick one, or configure a gated remote/OpenAI-compatible endpoint. Writes the
choice to config. Local-first: remote requires explicit opt-in and flips policy
to allow external, with a clear warning.
"""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from buster.cli import art
from buster.config import load_config, save_config
from buster.models.detect import detect_lan, detect_local


def run_provider_onboarding(console: Console) -> None:
    console.print(Panel(art.banner("Let's set up your model provider"),
                        title="Setup", border_style="cyan"))

    console.print("Looking for a model provider on this device…")
    local = asyncio.run(detect_local())

    # A local provider that's running but has no models isn't usable yet — call
    # that out and steer toward a LAN scan (models may live on another host).
    local_usable = [p for p in local if p.models]
    local_empty = [p for p in local if not p.models]
    for p in local_empty:
        console.print(f"[yellow]Found {p.kind} on this device but it has no models "
                      f"installed.[/] Pull one with e.g. [bold]ollama pull gemma3[/], "
                      f"or use a server on your network.")

    default_scan = True  # default to scanning; especially useful when local is empty
    scan = Confirm.ask("Scan the local network for Ollama / LM Studio servers?",
                       default=default_scan)
    if scan:
        console.print("[dim]Scanning the local network (a few seconds)…[/]")
    lan = asyncio.run(detect_lan(scan=scan)) if scan else []

    found = local + lan
    if found:
        table = Table(title="Detected providers")
        table.add_column("#"); table.add_column("Type"); table.add_column("Where")
        table.add_column("Endpoint"); table.add_column("Models")
        for i, p in enumerate(found, 1):
            models_txt = (", ".join(p.models[:3]) + ("…" if len(p.models) > 3 else "")) \
                if p.models else "[yellow](no models)[/]"
            table.add_row(str(i), p.kind, p.location, p.base_url, models_txt)
        console.print(table)
    else:
        console.print("[yellow]No local or LAN providers detected.[/]")

    # Default to the first provider that actually has models (usually the LAN
    # server when the local one is empty).
    first_usable = next((i for i, p in enumerate(found, 1) if p.models), None)
    default_choice = str(first_usable) if first_usable else ("1" if found else "s")

    console.print(
        "\nOptions:\n"
        "  [bold]1-N[/]     use a detected provider\n"
        "  [bold]r[/]       configure a remote / OpenAI-compatible endpoint "
        "([red]sends data off your network[/])\n"
        "  [bold]s[/]       skip for now"
    )
    choice = Prompt.ask("Choose", default=default_choice)

    config = load_config()
    if choice.lower() == "s":
        console.print("[dim]Skipped. Buster stays useful without a model; configure later with "
                      "'buster setup'.[/]")
        return
    if choice.lower() == "r":
        _configure_remote(console, config)
    else:
        try:
            idx = int(choice) - 1
            p = found[idx]
        except (ValueError, IndexError):
            console.print("[red]Invalid choice.[/]")
            return
        _apply_detected(config, p)
        console.print(f"[green]✓[/] Using {p.kind} at {p.base_url} ({p.location}).")

    config.onboarding.completed = True
    save_config(config)


def _apply_detected(config, p) -> None:
    if p.kind == "ollama":
        config.inference.default_provider = "ollama"
        if p.location == "device":
            config.inference.ollama_url = p.base_url
        elif p.base_url not in config.inference.lan_ollama_urls:
            config.inference.lan_ollama_urls.append(p.base_url)
    elif p.kind == "lmstudio":
        config.inference.default_provider = "lmstudio"
        if p.base_url not in config.inference.lmstudio_urls:
            config.inference.lmstudio_urls.append(p.base_url)
    if p.models:
        # Prefer a non-embedding model as the default.
        chat = next((m for m in p.models if "embed" not in m.lower()), p.models[0])
        config.inference.default_model = chat


def _configure_remote(console: Console, config) -> None:
    console.print(Panel(
        "[red]This sends your prompts to a service outside your local network.[/]\n"
        "Only use an endpoint you trust. Buster will label every response that "
        "leaves your network and record it in the audit log.",
        title="Remote provider", border_style="red"))
    if not Confirm.ask("Continue configuring a remote provider?", default=False):
        console.print("[dim]Cancelled. Staying local-first.[/]")
        return
    base_url = Prompt.ask("Base URL (OpenAI-compatible, incl. /v1)")
    name = Prompt.ask("Name", default="remote")
    api_key = Prompt.ask("API key (stored locally, redacted from logs)", password=True, default="")
    model = Prompt.ask("Default model id", default="")

    config.inference.remote.enabled = True
    config.inference.remote.name = name
    config.inference.remote.base_url = base_url
    config.inference.remote.api_key = api_key
    config.inference.remote.model = model
    config.inference.default_provider = "remote"
    # Remote is only *used* when policy permits external inference.
    config.inference.policy = "no_restriction"
    console.print(f"[green]✓[/] Remote provider '{name}' configured. "
                  "Policy set to allow external inference (data may leave your network).")
