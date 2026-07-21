"""Network health checks. Read-only; no aggressive scanning by default.

Any broader network scan must require explicit user approval and state scope —
enforced at the tool/permission layer, not here.
"""

from __future__ import annotations

import socket
import time

import httpx
import psutil

from buster.diagnostics.models import CheckResult, CheckStatus


def _port_open(host: str, port: int, timeout: float = 1.0) -> tuple[bool, float]:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.perf_counter() - start) * 1000
    except OSError:
        return False, 0.0


def check_interfaces() -> CheckResult:
    addrs = psutil.net_if_addrs()
    up = [name for name, s in psutil.net_if_stats().items() if s.isup]
    return CheckResult(
        check="network_interfaces",
        status=CheckStatus.OK if up else CheckStatus.WARNING,
        summary=f"{len(up)} interface(s) up",
        evidence={"up": up, "interfaces": list(addrs.keys())},
    )


def check_dns() -> CheckResult:
    try:
        start = time.perf_counter()
        socket.gethostbyname("one.one.one.one")
        ms = (time.perf_counter() - start) * 1000
        return CheckResult(
            check="dns_resolution",
            status=CheckStatus.OK,
            summary=f"DNS resolving ({ms:.0f} ms)",
            evidence={"latency_ms": round(ms)},
        )
    except OSError:
        return CheckResult(
            check="dns_resolution",
            status=CheckStatus.CRITICAL,
            summary="DNS resolution failed",
            recommendations=["Check DNS configuration / connectivity"],
        )


async def check_internet() -> CheckResult:
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            start = time.perf_counter()
            r = await c.get("https://one.one.one.one")
            ms = (time.perf_counter() - start) * 1000
        ok = r.status_code < 500
        return CheckResult(
            check="internet_reachability",
            status=CheckStatus.OK if ok else CheckStatus.WARNING,
            summary=f"Internet reachable ({ms:.0f} ms)" if ok else "Internet degraded",
            evidence={"latency_ms": round(ms), "status": r.status_code},
        )
    except Exception:  # noqa: BLE001
        return CheckResult(
            check="internet_reachability",
            status=CheckStatus.WARNING,
            summary="No internet reachability",
            recommendations=["Check gateway / connectivity (local features still work)"],
        )


def check_gateway() -> CheckResult:
    # Best-effort default gateway via a UDP socket trick (no packets sent).
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return CheckResult(
            check="default_gateway",
            status=CheckStatus.OK,
            summary=f"Local address {local_ip}",
            evidence={"local_ip": local_ip},
        )
    except OSError:
        return CheckResult(check="default_gateway", status=CheckStatus.WARNING, summary="No route")


def check_ollama_endpoint() -> CheckResult:
    ok, ms = _port_open("127.0.0.1", 11434)
    return CheckResult(
        check="ollama_endpoint",
        status=CheckStatus.OK if ok else CheckStatus.WARNING,
        summary=f"Ollama endpoint {'up' if ok else 'down'}" + (f" ({ms:.0f} ms)" if ok else ""),
        evidence={"reachable": ok},
    )


async def run_network_check() -> list[CheckResult]:
    results = [check_interfaces(), check_gateway(), check_dns()]
    results.append(await check_internet())
    results.append(check_ollama_endpoint())
    return results
