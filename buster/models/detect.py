"""Detect available inference providers on the device and the local network.

Used by onboarding to offer the user concrete choices. All probes are read-only
HTTP GETs to well-known local ports. LAN discovery is best-effort and bounded:
we check this host's /24 on the standard ports, plus any mDNS HTTP hosts.

Ports:
  Ollama    :11434  (/api/tags)
  LM Studio :1234   (/v1/models, OpenAI-compatible)
"""

from __future__ import annotations

import asyncio
import socket

import httpx
from pydantic import BaseModel

OLLAMA_PORT = 11434
LMSTUDIO_PORT = 1234


class DetectedProvider(BaseModel):
    kind: str            # ollama | lmstudio
    base_url: str
    location: str        # device | lan
    host: str
    models: list[str] = []
    reachable: bool = True


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


async def _probe_ollama(host: str, location: str) -> DetectedProvider | None:
    url = f"http://{host}:{OLLAMA_PORT}"
    try:
        async with httpx.AsyncClient(timeout=1.5) as c:
            r = await c.get(f"{url}/api/tags")
            if r.status_code != 200:
                return None
            models = [m.get("name", "") for m in r.json().get("models", [])]
        return DetectedProvider(kind="ollama", base_url=url, location=location, host=host, models=models)
    except Exception:  # noqa: BLE001
        return None


async def _probe_lmstudio(host: str, location: str) -> DetectedProvider | None:
    url = f"http://{host}:{LMSTUDIO_PORT}/v1"
    try:
        async with httpx.AsyncClient(timeout=1.5) as c:
            r = await c.get(f"{url}/models")
            if r.status_code != 200:
                return None
            models = [m.get("id", "") for m in r.json().get("data", [])]
        return DetectedProvider(kind="lmstudio", base_url=url, location=location, host=host, models=models)
    except Exception:  # noqa: BLE001
        return None


async def detect_local() -> list[DetectedProvider]:
    """Providers on this device (localhost)."""
    results = await asyncio.gather(
        _probe_ollama("127.0.0.1", "device"),
        _probe_lmstudio("127.0.0.1", "device"),
    )
    return [r for r in results if r]


async def detect_lan(scan: bool = True, max_hosts: int = 254) -> list[DetectedProvider]:
    """Scan the local /24 for Ollama / LM Studio servers (best-effort).

    Covers the full /24 (.1–.254) by default with short timeouts and bounded
    concurrency, so servers anywhere on the subnet are found. Only runs when the
    caller opts in (onboarding asks first) — Buster does not scan the network
    silently.
    """
    if not scan:
        return []
    ip = _local_ip()
    if ip == "127.0.0.1":
        return []
    prefix = ip.rsplit(".", 1)[0]
    last = min(max_hosts, 254)
    hosts = [f"{prefix}.{i}" for i in range(1, last + 1) if f"{prefix}.{i}" != ip]

    sem = asyncio.Semaphore(64)

    async def _check(host: str) -> list[DetectedProvider]:
        async with sem:
            found = await asyncio.gather(_probe_ollama(host, "lan"), _probe_lmstudio(host, "lan"))
            return [f for f in found if f]

    batches = await asyncio.gather(*(_check(h) for h in hosts))
    out: list[DetectedProvider] = []
    for b in batches:
        out.extend(b)
    return out


async def detect_all(scan_lan: bool = False) -> list[DetectedProvider]:
    local = await detect_local()
    lan = await detect_lan(scan=scan_lan)
    return local + lan
