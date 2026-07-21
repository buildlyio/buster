"""Linux-specific diagnostic adapter."""

from __future__ import annotations

import os

from buster.diagnostics.models import CheckResult, CheckStatus


def load_average() -> CheckResult:
    try:
        one, five, fifteen = os.getloadavg()
        return CheckResult(
            check="load_average",
            status=CheckStatus.OK,
            summary=f"Load {one:.2f} / {five:.2f} / {fifteen:.2f}",
            evidence={"1m": one, "5m": five, "15m": fifteen},
        )
    except (OSError, AttributeError):
        return CheckResult(check="load_average", status=CheckStatus.UNKNOWN, summary="Unavailable")


def extra_checks() -> list[CheckResult]:
    return [load_average()]
