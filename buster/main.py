"""Module entrypoint: `python -m buster.main [serve|...]` delegates to the CLI."""

from __future__ import annotations

from buster.cli.main import app

if __name__ == "__main__":
    app()
