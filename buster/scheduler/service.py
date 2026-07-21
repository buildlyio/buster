"""Background scheduler: polls deterministic checks and raises/resolves alerts.

Runs as an asyncio task inside the API process. Requires no LLM. Alert codes:
  buster_unavailable, ollama_unavailable, low_disk, high_memory,
  lan_model_unavailable, dns_failure, node_unavailable
"""

from __future__ import annotations

import asyncio
import socket

import psutil

from buster.config import load_config
from buster.events import Event, EventType, get_event_bus
from buster.scheduler.alerts import get_alerts


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class Scheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            cfg = load_config()
            if cfg.scheduler.enabled:
                await self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=cfg.scheduler.poll_interval_seconds)
            except TimeoutError:
                pass

    async def run_once(self) -> list[dict]:
        cfg = load_config()
        alerts = get_alerts()
        raised: list[dict] = []

        # Ollama
        if _port_open("127.0.0.1", 11434):
            alerts.resolve("ollama_unavailable")
        else:
            a = alerts.raise_alert("ollama_unavailable", "Ollama unavailable",
                                   detail="Ollama endpoint :11434 is not reachable.")
            if a:
                raised.append(a.model_dump())

        # Disk
        du = psutil.disk_usage("/")
        if du.percent >= cfg.scheduler.low_disk_percent:
            a = alerts.raise_alert("low_disk", "Low disk space", severity="warning",
                                   detail=f"Disk {du.percent:.0f}% used.")
            if a:
                raised.append(a.model_dump())
        else:
            alerts.resolve("low_disk")

        # Memory
        vm = psutil.virtual_memory()
        if vm.percent >= cfg.scheduler.high_memory_percent:
            a = alerts.raise_alert("high_memory", "High memory usage", severity="warning",
                                   detail=f"Memory {vm.percent:.0f}% used.")
            if a:
                raised.append(a.model_dump())
        else:
            alerts.resolve("high_memory")

        # DNS
        try:
            socket.gethostbyname("one.one.one.one")
            alerts.resolve("dns_failure")
        except OSError:
            a = alerts.raise_alert("dns_failure", "DNS resolution failure",
                                   detail="Could not resolve a known hostname.")
            if a:
                raised.append(a.model_dump())

        # LAN models
        for url in cfg.inference.lan_ollama_urls:
            host = url.split("//")[-1].split(":")[0]
            port = int(url.split(":")[-1].split("/")[0]) if ":" in url.split("//")[-1] else 11434
            if not _port_open(host, port):
                a = alerts.raise_alert("lan_model_unavailable",
                                       f"Configured LAN model unavailable ({url})")
                if a:
                    raised.append(a.model_dump())

        for a in raised:
            await get_event_bus().publish(
                Event(type=EventType.ALERT_CREATED, title=a["title"],
                      metadata={"code": a["code"], "severity": a["severity"]})
            )
        return raised
