"""Buster's ASCII art. Buster is a rabbit. Brought to you by buildly.io."""

from __future__ import annotations

# Original ASCII-art rabbit for CLI banners and the installer. Pure ASCII so it
# renders identically in every terminal.
RABBIT = r"""
     (\_/)
     (o.o)     B U S T E R
     (> <)     your local-first assistant
"""

# A taller variant for the interactive banner header.
RABBIT_LARGE = r"""
      (\_/)
      ( o.o )
      ( > < )
     __(   )__      B U S T E R
    /  `---'  \     local-first assistant
"""

TAGLINE = "brought to you by buildly.io"


def banner(subtitle: str = "") -> str:
    """Return the rabbit banner with an optional subtitle line + tagline."""
    lines = [RABBIT.rstrip("\n")]
    if subtitle:
        lines.append(f"  {subtitle}")
    lines.append(f"  {TAGLINE}")
    return "\n".join(lines)
