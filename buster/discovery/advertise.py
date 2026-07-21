"""mDNS/Bonjour advertising so `http://buster.local` resolves on the LAN and
other Buster nodes can discover this one.

Best-effort: if zeroconf is unavailable or registration fails (common on
locked-down networks), Buster logs and continues — the localhost URL always
works. Advertising is gated by ``discovery.advertise_buster``.

Inside the server's asyncio lifespan we must use ``AsyncZeroconf`` — the
synchronous ``Zeroconf`` starts its own loop machinery and fails when created
from within a running event loop. ``start_advertising`` (sync) is kept for
non-async callers; ``start_advertising_async`` is used by the app lifespan.
"""

from __future__ import annotations

import logging
import socket

from buster.config import load_config

log = logging.getLogger("buster.discovery")

# Module-level handles so we can unregister on shutdown.
_zc = None          # sync Zeroconf
_azc = None         # AsyncZeroconf
_info = None


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


def _build_info():
    from zeroconf import ServiceInfo

    config = load_config()
    ip = _local_ip()
    port = config.server.port
    # mDNS can only publish a ".local" hostname. If the configured hostname uses
    # another suffix (e.g. "buster.home" served by Pi-hole/local DNS), we still
    # advertise "buster.local" over mDNS and record the configured name in TXT;
    # the non-.local name must be created in that DNS server (see docs/INSTALL).
    configured = config.server.hostname or "buster.local"
    mdns_host = configured if configured.endswith(".local") else "buster.local"
    # Advertise an HTTP service whose TXT points at the LCDP manifest path, so
    # peers can discover Buster and fetch its capability manifest.
    return ServiceInfo(
        type_="_http._tcp.local.",
        name=f"Buster ({socket.gethostname()})._http._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={
            b"product": b"buster",
            b"lcdp": b"/.well-known/lcdp.json",
            b"path": b"/",
            b"hostname": configured.encode(),
        },
        server=mdns_host.rstrip(".") + ".",
    ), ip, port


def _enabled() -> bool:
    config = load_config()
    return config.discovery.enabled and config.discovery.advertise_buster


# -- async (used by the server lifespan) -------------------------------------

async def start_advertising_async() -> bool:
    global _azc, _info
    if not _enabled():
        return False
    try:
        from zeroconf.asyncio import AsyncZeroconf
    except Exception as exc:  # noqa: BLE001
        log.info("zeroconf not available; skipping mDNS advertising (%r)", exc)
        return False
    try:
        _info, ip, port = _build_info()
        _azc = AsyncZeroconf()
        await _azc.async_register_service(_info, allow_name_change=True)
        log.info("Advertising buster.local on %s:%s via mDNS", ip, port)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("mDNS advertising failed (%r); localhost URL still works", exc)
        await stop_advertising_async()
        return False


async def stop_advertising_async() -> None:
    global _azc, _info
    try:
        if _azc and _info:
            await _azc.async_unregister_service(_info)
    except Exception:  # noqa: BLE001
        pass
    finally:
        if _azc:
            try:
                await _azc.async_close()
            except Exception:  # noqa: BLE001
                pass
        _azc = None
        _info = None


# -- sync (standalone / non-async callers) -----------------------------------

def start_advertising() -> bool:
    global _zc, _info
    if not _enabled():
        return False
    try:
        from zeroconf import Zeroconf
    except Exception as exc:  # noqa: BLE001
        log.info("zeroconf not available; skipping mDNS advertising (%r)", exc)
        return False
    try:
        _info, ip, port = _build_info()
        _zc = Zeroconf()
        _zc.register_service(_info, allow_name_change=True)
        log.info("Advertising buster.local on %s:%s via mDNS", ip, port)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("mDNS advertising failed (%r); localhost URL still works", exc)
        stop_advertising()
        return False


def stop_advertising() -> None:
    global _zc, _info
    try:
        if _zc and _info:
            _zc.unregister_service(_info)
    except Exception:  # noqa: BLE001
        pass
    finally:
        if _zc:
            try:
                _zc.close()
            except Exception:  # noqa: BLE001
                pass
        _zc = None
        _info = None
