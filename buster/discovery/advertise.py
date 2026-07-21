"""mDNS/Bonjour advertising so Buster resolves on the LAN and other Buster
nodes can discover it.

Multiple Busters can share a LAN, so each node advertises a UNIQUE hostname
``<node>.buster.local`` (plus an optional bare ``buster.local`` alias for the
single-node case). See ``buster.discovery.naming``.

mDNS can only publish ``.local`` names. If ``server.domain`` uses another suffix
(e.g. ``buster.home`` via Pi-hole/local DNS), Buster advertises the equivalent
``.local`` names over mDNS and ``buster doctor`` prints the exact A records to
add to that DNS server.

Best-effort: if zeroconf is unavailable or registration fails (common on
locked-down networks), Buster logs and continues — the localhost URL always
works. Advertising is gated by ``discovery.advertise_buster``.

Inside the server's asyncio lifespan we must use ``AsyncZeroconf`` — the
synchronous ``Zeroconf`` starts its own loop machinery and fails when created
from within a running event loop.
"""

from __future__ import annotations

import logging
import socket

from buster.config import load_config
from buster.discovery import naming

log = logging.getLogger("buster.discovery")

# Module-level handles so we can unregister on shutdown.
_zc = None          # sync Zeroconf
_azc = None         # AsyncZeroconf
_infos: list = []   # registered ServiceInfo objects


def _local_ip() -> str:
    """Best-effort primary LAN IPv4 (no packets actually sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _mdns_host(name: str) -> str:
    """Map any Buster name to the .local host mDNS will actually publish.

    ``alderaan.buster.home`` -> ``alderaan.buster.local``
    ``buster.home``          -> ``buster.local``
    ``.local`` names pass through unchanged.
    """
    if name.endswith(".local"):
        return name
    # Replace the trailing domain suffix with ".local", keep any node prefix.
    dom = naming.domain()
    if name == dom:
        return "buster.local"
    if name.endswith("." + dom):
        prefix = name[: -(len(dom) + 1)]
        return f"{prefix}.buster.local"
    return name.split(".")[0] + ".buster.local"


def _build_infos():
    """Return (list[ServiceInfo], ip, port) for every name this node answers to."""
    from zeroconf import ServiceInfo

    config = load_config()
    ip = _local_ip()
    port = config.server.port
    addr = socket.inet_aton(ip)
    names = naming.all_names()
    primary = names[0]

    infos = []
    for i, name in enumerate(names):
        host = _mdns_host(name).rstrip(".") + "."
        # Distinct service-instance label per name so they don't collide.
        label = "Buster" if i == 0 else f"Buster alias {i}"
        infos.append(
            ServiceInfo(
                type_="_http._tcp.local.",
                name=f"{label} ({naming.node_slug()})._http._tcp.local.",
                addresses=[addr],
                port=port,
                properties={
                    b"product": b"buster",
                    b"lcdp": b"/.well-known/lcdp.json",
                    b"path": b"/",
                    b"node": naming.node_slug().encode(),
                    b"name": primary.encode(),
                },
                server=host,
            )
        )
    return infos, ip, port


def _enabled() -> bool:
    config = load_config()
    return config.discovery.enabled and config.discovery.advertise_buster


# -- async (used by the server lifespan) -------------------------------------

async def start_advertising_async() -> bool:
    global _azc, _infos
    if not _enabled():
        return False
    try:
        from zeroconf.asyncio import AsyncZeroconf
    except Exception as exc:  # noqa: BLE001
        log.info("zeroconf not available; skipping mDNS advertising (%r)", exc)
        return False
    try:
        _infos, ip, port = _build_infos()
        _azc = AsyncZeroconf()
        for info in _infos:
            await _azc.async_register_service(info, allow_name_change=True)
        log.info("Advertising %s on %s:%s via mDNS", naming.all_names(), ip, port)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("mDNS advertising failed (%r); localhost URL still works", exc)
        await stop_advertising_async()
        return False


async def stop_advertising_async() -> None:
    global _azc, _infos
    try:
        if _azc:
            for info in _infos:
                await _azc.async_unregister_service(info)
    except Exception:  # noqa: BLE001
        pass
    finally:
        if _azc:
            try:
                await _azc.async_close()
            except Exception:  # noqa: BLE001
                pass
        _azc = None
        _infos = []


# -- sync (standalone / non-async callers) -----------------------------------

def start_advertising() -> bool:
    global _zc, _infos
    if not _enabled():
        return False
    try:
        from zeroconf import Zeroconf
    except Exception as exc:  # noqa: BLE001
        log.info("zeroconf not available; skipping mDNS advertising (%r)", exc)
        return False
    try:
        _infos, ip, port = _build_infos()
        _zc = Zeroconf()
        for info in _infos:
            _zc.register_service(info, allow_name_change=True)
        log.info("Advertising %s on %s:%s via mDNS", naming.all_names(), ip, port)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("mDNS advertising failed (%r); localhost URL still works", exc)
        stop_advertising()
        return False


def stop_advertising() -> None:
    global _zc, _infos
    try:
        if _zc:
            for info in _infos:
                _zc.unregister_service(info)
    except Exception:  # noqa: BLE001
        pass
    finally:
        if _zc:
            try:
                _zc.close()
            except Exception:  # noqa: BLE001
                pass
        _zc = None
        _infos = []
