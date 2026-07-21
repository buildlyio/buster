"""Best-effort mDNS/DNS-SD discovery of HTTP services on the LAN.

Optional: if zeroconf isn't available or times out, discovery degrades to the
manually-configured service URLs. Read-only; found hosts are probed for
/.well-known/lcdp.json — never connected to automatically.
"""

from __future__ import annotations

import asyncio


async def discover_http_services(timeout: float = 3.0) -> list[str]:
    """Return candidate base URLs (http://host:port) for LCDP probing."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except Exception:  # noqa: BLE001
        return []

    found: list[str] = []

    class _Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, timeout=1500)
            if not info:
                return
            for addr in info.parsed_addresses():
                found.append(f"http://{addr}:{info.port}")

        def update_service(self, *a):  # required by newer zeroconf
            pass

        def remove_service(self, *a):
            pass

    def _scan() -> None:
        zc = Zeroconf()
        try:
            ServiceBrowser(zc, "_http._tcp.local.", _Listener())
            import time

            time.sleep(timeout)
        finally:
            zc.close()

    await asyncio.to_thread(_scan)
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for url in found:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out
