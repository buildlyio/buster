"""Raspberry Pi adapter — the minimum performance tier, NOT the core design.

Adds Pi-specific checks (throttling, temperature) on top of the Linux adapter.
"""

from __future__ import annotations

from pathlib import Path

from buster.diagnostics import linux
from buster.diagnostics.models import CheckResult, CheckStatus


def temperature() -> CheckResult:
    zone = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        milli = int(zone.read_text().strip())
        celsius = milli / 1000.0
        status = CheckStatus.OK if celsius < 75 else CheckStatus.WARNING
        if celsius >= 85:
            status = CheckStatus.CRITICAL
        return CheckResult(
            check="soc_temperature",
            status=status,
            summary=f"SoC temperature {celsius:.1f}°C",
            evidence={"celsius": celsius},
            recommendations=["Improve cooling / reduce load"] if status != CheckStatus.OK else [],
        )
    except (OSError, ValueError):
        return CheckResult(check="soc_temperature", status=CheckStatus.UNKNOWN, summary="Unavailable")


def extra_checks() -> list[CheckResult]:
    return [*linux.extra_checks(), temperature()]
