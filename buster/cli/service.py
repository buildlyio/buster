"""Local service control: start/stop/status/logs of the Buster Core process.

Uses a simple pidfile + subprocess so `buster start` works even before the
user-level service (systemd/launchd) is installed. The installed service runs
the same `buster serve` entrypoint.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import httpx

from buster.config import get_paths, load_config


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid() -> int | None:
    pf = get_paths().pid_file
    if not pf.exists():
        return None
    try:
        pid = int(pf.read_text().strip())
    except (ValueError, OSError):
        return None
    return pid if _pid_running(pid) else None


def start() -> tuple[bool, str]:
    if read_pid():
        return True, "Buster is already running."
    paths = get_paths()
    log = (paths.logs_dir / "buster.log").open("a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "buster.main", "serve"],
        stdout=log, stderr=log, start_new_session=True,
    )
    paths.pid_file.write_text(str(proc.pid))
    # Wait briefly for the API to come up.
    config = load_config()
    for _ in range(30):
        try:
            httpx.get(f"{config.base_url}/api/health", timeout=1.0)
            return True, "Buster started."
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    return True, "Buster starting (API not yet responding)."


def stop() -> tuple[bool, str]:
    pid = read_pid()
    if not pid:
        return True, "Buster is not running."
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    get_paths().pid_file.unlink(missing_ok=True)
    return True, "Buster stopped."


def status() -> dict:
    pid = read_pid()
    config = load_config()
    # Probe the API regardless of the pidfile — the service may have been
    # started by systemd/launchd (or another process) that we didn't spawn.
    api_ok = False
    try:
        r = httpx.get(f"{config.base_url}/api/health", timeout=1.5)
        api_ok = r.status_code == 200
    except Exception:  # noqa: BLE001
        api_ok = False
    return {"running": bool(pid) or api_ok, "pid": pid, "api_reachable": api_ok, "url": config.base_url}


def logs(lines: int = 40) -> str:
    log_file = get_paths().logs_dir / "buster.log"
    if not log_file.exists():
        return "(no logs yet)"
    content = log_file.read_text(errors="replace").splitlines()
    return "\n".join(content[-lines:])
