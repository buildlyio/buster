"""Concise in-terminal getting-started walkthrough (`buster guide` / `/guide`).

Adapts to what's already set up: it checks whether a model is connected and
points at the right next step. Full guide: docs/GETTING_STARTED.md.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from buster.cli import art
from buster.config import load_config


def print_guide(console: Console) -> None:
    config = load_config()
    has_model = bool(config.inference.default_model)

    steps = [
        ("1. Connect a model",
         "[green]done[/] — " + config.inference.default_model if has_model
         else "[yellow]run[/] [bold]buster setup[/]  (detects local + LAN model servers)"),
        ("2. Chat & research",
         "buster ask \"what can you do?\"   ·   buster research \"a topic\""),
        ("3. Checks (no model needed)",
         "buster doctor   ·   buster system check   ·   buster network check"),
        ("4. Developer workflow",
         "buster dev   ·   buster adopt   ·   buster work <issue>   ·   buster labs status"),
        ("5. Manage",
         "buster status | start | stop | logs   ·   buster open   ·   buster update"),
    ]
    body_lines = [f"{art.RABBIT.strip(chr(10))}", ""]
    for title, detail in steps:
        body_lines.append(f"[bold]{title}[/]")
        body_lines.append(f"   {detail}")
    body_lines.append("")
    body_lines.append("[dim]Full guide: docs/GETTING_STARTED.md · "
                      "brought to you by buildly.io[/]")
    console.print(Panel("\n".join(body_lines), title="Getting started with Buster",
                        border_style="cyan"))
