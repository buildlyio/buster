"""Filesystem paths for Buster data, config, cache, and logs.

Follows XDG on Linux and Application Support / Library on macOS, but everything
can be overridden with the ``BUSTER_HOME`` environment variable (used by tests
and portable installs).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _default_home() -> Path:
    override = os.environ.get("BUSTER_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Buster"
    # Linux / other: XDG data dir
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "buster"


@dataclass(frozen=True)
class BusterPaths:
    """Resolved paths. All directories are created on first access."""

    home: Path

    @property
    def config_file(self) -> Path:
        return self.home / "config.toml"

    @property
    def data_dir(self) -> Path:
        return self.home / "data"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "buster.db"

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def research_dir(self) -> Path:
        return self.data_dir / "research"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def skills_dir(self) -> Path:
        """User-installed skills (bundled skills live inside the package)."""
        return self.home / "skills"

    @property
    def toolpacks_dir(self) -> Path:
        return self.home / "toolpacks"

    @property
    def run_dir(self) -> Path:
        """Runtime files: pid, socket hints, service state."""
        return self.home / "run"

    @property
    def pid_file(self) -> Path:
        return self.run_dir / "buster.pid"

    def ensure(self) -> BusterPaths:
        for d in (
            self.home,
            self.data_dir,
            self.cache_dir,
            self.logs_dir,
            self.memory_dir,
            self.research_dir,
            self.reports_dir,
            self.skills_dir,
            self.toolpacks_dir,
            self.run_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return self


@lru_cache(maxsize=1)
def get_paths() -> BusterPaths:
    """Return the singleton paths object, creating directories on first call."""
    return BusterPaths(home=_default_home()).ensure()
