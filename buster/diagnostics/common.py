"""Cross-platform system checks built on psutil. Read-only.

OS-specific detail lives in linux.py / macos.py / raspberry_pi.py adapters,
selected by ``get_adapter()``. Raspberry Pi is an adapter, not the core.
"""

from __future__ import annotations

import shutil
import socket

import psutil

from buster.config import load_config
from buster.diagnostics.models import CheckResult, CheckStatus


def check_cpu() -> CheckResult:
    pct = psutil.cpu_percent(interval=0.3)
    status = CheckStatus.OK if pct < 85 else CheckStatus.WARNING
    return CheckResult(
        check="cpu_usage",
        status=status,
        summary=f"CPU usage {pct:.0f}%",
        evidence={"percent": pct, "cores": psutil.cpu_count()},
    )


def check_memory() -> CheckResult:
    vm = psutil.virtual_memory()
    cfg = load_config()
    threshold = cfg.scheduler.high_memory_percent
    status = CheckStatus.OK
    recs: list[str] = []
    if vm.percent >= threshold:
        status = CheckStatus.WARNING
        recs = ["Unload the current model", "Select a smaller model", "Close memory-heavy apps"]
    if vm.available < 256 * 1024 * 1024:
        status = CheckStatus.CRITICAL
    return CheckResult(
        check="memory_pressure",
        status=status,
        summary=f"Memory {vm.percent:.0f}% used, {vm.available / 1024**2:.0f} MB available",
        evidence={"percent": vm.percent, "available_mb": round(vm.available / 1024**2)},
        recommendations=recs,
    )


def check_swap() -> CheckResult:
    sw = psutil.swap_memory()
    status = CheckStatus.OK if sw.percent < 50 else CheckStatus.WARNING
    return CheckResult(
        check="swap_usage",
        status=status,
        summary=f"Swap {sw.percent:.0f}% used",
        evidence={"used_mb": round(sw.used / 1024**2), "percent": sw.percent},
    )


def check_disk() -> CheckResult:
    du = psutil.disk_usage("/")
    cfg = load_config()
    threshold = cfg.scheduler.low_disk_percent
    status = CheckStatus.OK if du.percent < threshold else CheckStatus.WARNING
    if du.percent >= 97:
        status = CheckStatus.CRITICAL
    return CheckResult(
        check="disk_usage",
        status=status,
        summary=f"Disk {du.percent:.0f}% used, {du.free / 1024**3:.0f} GB free",
        evidence={"percent": du.percent, "free_gb": round(du.free / 1024**3, 1)},
        recommendations=["Free disk space or clear caches"] if status != CheckStatus.OK else [],
    )


def top_processes(limit: int = 10) -> CheckResult:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda i: (i.get("memory_percent") or 0), reverse=True)
    top = procs[:limit]
    return CheckResult(
        check="top_processes",
        status=CheckStatus.OK,
        summary=f"Top {len(top)} processes by memory",
        evidence={"processes": top},
    )


def check_hostname() -> CheckResult:
    return CheckResult(
        check="hostname",
        status=CheckStatus.OK,
        summary=socket.gethostname(),
        evidence={"hostname": socket.gethostname(), "fqdn": socket.getfqdn()},
    )


def check_ollama() -> CheckResult:
    installed = shutil.which("ollama") is not None
    reachable = _port_open("127.0.0.1", 11434)
    if reachable:
        status, summary = CheckStatus.OK, "Ollama service reachable on :11434"
        recs: list[str] = []
    elif installed:
        status = CheckStatus.WARNING
        summary = "Ollama installed but service not reachable"
        recs = ["Start the Ollama service"]
    else:
        status = CheckStatus.WARNING
        summary = "Ollama not installed"
        recs = ["Install Ollama to enable local inference"]
    return CheckResult(
        check="ollama_status",
        status=status,
        summary=summary,
        evidence={"installed": installed, "reachable": reachable},
        recommendations=recs,
    )


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
