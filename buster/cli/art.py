"""Buster's ASCII art — Buster the Buildly Rabbit.

The canonical rabbit and tagline are the established Buildly identity (from the
Buildly CLI). Pure ASCII so it renders identically in every terminal.
"""

from __future__ import annotations

# Canonical Buster the Buildly Rabbit.
RABBIT = r"""
    /\_/\
   ( o.o )   B U S T E R
    > ^ <    your local-first assistant
"""

# Banner variant with the identity line beside it.
RABBIT_LARGE = r"""
    /\_/\
   ( o.o )   Buster the Buildly Rabbit
    > ^ <    your local-first assistant
"""

TAGLINE = "Buildly.io - Build Smarter, Not Harder"


def banner(subtitle: str = "") -> str:
    """Return the rabbit banner with an optional subtitle line + tagline."""
    lines = [RABBIT.rstrip("\n")]
    if subtitle:
        lines.append(f"  {subtitle}")
    lines.append(f"  {TAGLINE}")
    return "\n".join(lines)
