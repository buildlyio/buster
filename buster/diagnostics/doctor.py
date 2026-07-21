"""``buster doctor`` — inspects Buster itself, deterministically (no LLM).

Checks: service status, API reachability, DB health, cache state, Ollama
reachability, local DNS/mDNS, port conflicts, config errors, tool-pack load.
"""

from __future__ import annotations

import socket

import httpx
from pydantic import BaseModel

from buster.config import get_paths, load_config
from buster.diagnostics.models import CheckResult, CheckStatus, worst


class DoctorReport(BaseModel):
    status: CheckStatus
    checks: list[CheckResult]

    def render_lines(self) -> list[str]:
        icon = {
            CheckStatus.OK: "✓",
            CheckStatus.WARNING: "!",
            CheckStatus.CRITICAL: "✕",
            CheckStatus.UNKNOWN: "?",
        }
        lines = []
        for c in self.checks:
            lines.append(f"  {icon[c.status]} {c.check}: {c.summary}")
            for rec in c.recommendations:
                lines.append(f"      → {rec}")
        return lines


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def run_doctor() -> DoctorReport:
    config = load_config()
    paths = get_paths()
    checks: list[CheckResult] = []

    # Config
    try:
        load_config()
        checks.append(CheckResult(check="config", status=CheckStatus.OK, summary="Configuration valid"))
    except Exception as exc:  # noqa: BLE001
        checks.append(
            CheckResult(
                check="config",
                status=CheckStatus.CRITICAL,
                summary=f"Config error: {exc}",
                recommendations=["Fix or delete config.toml to restore defaults"],
            )
        )

    # Database
    try:
        from buster.database import get_database

        db = get_database()
        version = db.schema_version
        checks.append(
            CheckResult(
                check="database",
                status=CheckStatus.OK,
                summary=f"SQLite healthy (schema v{version})",
                evidence={"path": str(paths.db_file), "schema_version": version},
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            CheckResult(check="database", status=CheckStatus.CRITICAL, summary=f"DB error: {exc}")
        )

    # API reachability
    api_up = _port_open(config.server.host, config.server.port)
    if api_up:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{config.base_url}/api/health")
            ok = r.status_code == 200
            checks.append(
                CheckResult(
                    check="api",
                    status=CheckStatus.OK if ok else CheckStatus.WARNING,
                    summary="API reachable" if ok else f"API returned {r.status_code}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                CheckResult(check="api", status=CheckStatus.WARNING, summary=f"API error: {exc}")
            )
    else:
        checks.append(
            CheckResult(
                check="api",
                status=CheckStatus.WARNING,
                summary=f"API not listening on {config.server.host}:{config.server.port}",
                recommendations=["Run 'buster start' to launch the service"],
            )
        )

    # Cache state
    try:
        size_mb = _dir_size_mb(paths.cache_dir)
        limit = config.cache.disk_limit_mb
        status = CheckStatus.OK if size_mb <= limit else CheckStatus.WARNING
        checks.append(
            CheckResult(
                check="cache",
                status=status,
                summary=f"Cache {size_mb:.1f} MB / {limit} MB limit",
                recommendations=["Run 'buster config' or clear cache"] if status != CheckStatus.OK else [],
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(CheckResult(check="cache", status=CheckStatus.UNKNOWN, summary=str(exc)))

    # Ollama
    ollama_up = _port_open("127.0.0.1", 11434)
    checks.append(
        CheckResult(
            check="ollama",
            status=CheckStatus.OK if ollama_up else CheckStatus.WARNING,
            summary="Ollama reachable on :11434" if ollama_up else "Ollama not reachable",
            recommendations=[] if ollama_up else ["Start Ollama, or chat features stay disabled"],
        )
    )

    # Port conflict (someone else on our port but API not ours)
    if _port_open(config.server.host, config.server.port) and not api_up:
        checks.append(
            CheckResult(
                check="port",
                status=CheckStatus.WARNING,
                summary=f"Port {config.server.port} in use by another process",
            )
        )

    # mDNS / local name resolution
    try:
        socket.gethostbyname("localhost")
        checks.append(CheckResult(check="dns", status=CheckStatus.OK, summary="Local name resolution OK"))
    except Exception:  # noqa: BLE001
        checks.append(
            CheckResult(check="dns", status=CheckStatus.WARNING, summary="localhost did not resolve")
        )

    # Tool-pack load
    try:
        from buster.tools import get_registry

        reg = get_registry()
        checks.append(
            CheckResult(
                check="tools",
                status=CheckStatus.OK,
                summary=f"{len(reg.all())} tools loaded across {len(reg.packs())} packs",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            CheckResult(check="tools", status=CheckStatus.WARNING, summary=f"Tool load issue: {exc}")
        )

    return DoctorReport(status=worst(checks), checks=checks)


def _dir_size_mb(path) -> float:
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return total / (1024**2)
