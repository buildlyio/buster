"""Developer tooling integration: bb-code (codegen) + tokenjam (token telemetry).

Buster coexists with these MIT/OSS tools — it detects them, offers to install
them (only with explicit approval; never silently), and surfaces their output.
It never vendors their code. tokenjam is read-only: Buster reads its local
findings and sends it nothing.
"""

from buster.dev.setup import (
    DevToolStatus,
    dev_status,
    install_command,
    tokenjam_summary,
)

__all__ = ["DevToolStatus", "dev_status", "install_command", "tokenjam_summary"]
