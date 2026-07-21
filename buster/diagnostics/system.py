"""System health check runner: common checks + OS adapter checks."""

from __future__ import annotations

from buster.diagnostics import common
from buster.diagnostics.models import CheckResult
from buster.models.capability import detect_capabilities


def _adapter():
    prof = detect_capabilities()
    if prof.is_raspberry_pi:
        from buster.diagnostics import raspberry_pi

        return raspberry_pi
    if prof.platform == "linux":
        from buster.diagnostics import linux

        return linux
    if prof.platform == "macos":
        from buster.diagnostics import macos

        return macos
    return None


def run_system_check() -> list[CheckResult]:
    results = [
        common.check_cpu(),
        common.check_memory(),
        common.check_swap(),
        common.check_disk(),
        common.check_hostname(),
        common.check_ollama(),
        common.top_processes(),
    ]
    adapter = _adapter()
    if adapter is not None:
        results.extend(adapter.extra_checks())
    return results
