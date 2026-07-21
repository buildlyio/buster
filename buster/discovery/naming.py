"""LAN naming: derive per-host Buster names so multiple nodes coexist.

Scheme:
    <node_name>.<domain>     unique per machine (e.g. alderaan.buster.home)
    <domain>                 optional bare alias (buster.local / buster.home)

`node_name` defaults to a slug of the machine's short hostname.
"""

from __future__ import annotations

import re
import socket

from buster.config import load_config


def _slug(text: str) -> str:
    """DNS-label-safe slug: lowercase, alnum + hyphen, no leading/trailing hyphen."""
    s = re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
    return s or "buster"


def node_slug() -> str:
    """This node's label (config override, else derived from the hostname)."""
    cfg = load_config()
    if cfg.server.node_name:
        return _slug(cfg.server.node_name)
    # Short hostname, without any existing domain suffix.
    host = socket.gethostname().split(".")[0]
    return _slug(host)


def domain() -> str:
    return load_config().server.domain.strip(".") or "buster.local"


def primary_name() -> str:
    """Unique fully-qualified name for this node, e.g. alderaan.buster.home."""
    return f"{node_slug()}.{domain()}"


def alias_name() -> str | None:
    """The bare convenience alias (buster.local / buster.home), or None."""
    return domain() if load_config().server.advertise_alias else None


def all_names() -> list[str]:
    """Every name this node answers to (primary first, then alias)."""
    names = [primary_name()]
    alias = alias_name()
    if alias and alias not in names:
        names.append(alias)
    return names


def needs_manual_dns() -> bool:
    """True when the domain is not .local (mDNS can't publish it)."""
    return not domain().endswith(".local")


def dns_records(ip: str | None = None) -> list[tuple[str, str]]:
    """A records to add to a local DNS server (Pi-hole/router) for non-.local
    domains. Returns (name, ip) pairs. Empty for .local domains (mDNS handles
    those automatically)."""
    if not needs_manual_dns():
        return []
    if ip is None:
        ip = _local_ip()
    return [(name, ip) for name in all_names()]


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"
