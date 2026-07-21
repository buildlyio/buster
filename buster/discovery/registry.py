"""Discovery registry: persist discovered services/nodes + trust decisions.

Discovery mechanisms (Phase 1):
  * manually configured service URLs (config.discovery.service_urls)
  * /.well-known/lcdp.json fetch
  * mDNS/DNS-SD (best-effort via zeroconf; optional)

Buster never connects automatically — trust is an explicit user decision.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache

import httpx

from buster.database import get_database
from buster.discovery.lcdp import LCDPManifest


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class DiscoveryRegistry:
    # -- services -------------------------------------------------------------

    def record_service(self, manifest: LCDPManifest) -> None:
        db = get_database()
        now = _now()
        existing = db.query_one("SELECT trust FROM services WHERE id = ?", (manifest.id,))
        trust = existing["trust"] if existing else "discovered"
        db.execute(
            "INSERT INTO services (id, name, product, version, host, manifest, trust, "
            "discovered_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, product=excluded.product, "
            "version=excluded.version, manifest=excluded.manifest, last_seen_at=excluded.last_seen_at",
            (manifest.id, manifest.name, manifest.product, manifest.version, manifest.host,
             manifest.model_dump_json(by_alias=True), trust, now, now),
        )

    def list_services(self) -> list[dict]:
        rows = get_database().query("SELECT * FROM services ORDER BY discovered_at DESC")
        return [self._svc_row(r) for r in rows]

    def set_service_trust(self, service_id: str, trust: str) -> None:
        get_database().execute("UPDATE services SET trust = ? WHERE id = ?", (trust, service_id))

    def _svc_row(self, r) -> dict:
        d = dict(r)
        d["manifest"] = json.loads(d["manifest"]) if d["manifest"] else {}
        return d

    # -- nodes ----------------------------------------------------------------

    def record_node(self, manifest: LCDPManifest) -> None:
        db = get_database()
        now = _now()
        existing = db.query_one("SELECT trust FROM nodes WHERE id = ?", (manifest.id,))
        trust = existing["trust"] if existing else "discovered"
        meta = manifest.model_dump(by_alias=True)
        db.execute(
            "INSERT INTO nodes (id, name, device_type, platform, api_url, manifest, trust, "
            "discovered_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, manifest=excluded.manifest, "
            "last_seen_at=excluded.last_seen_at",
            (manifest.id, manifest.name, meta.get("device_type", ""), meta.get("platform", ""),
             manifest.api_url, manifest.model_dump_json(by_alias=True), trust, now, now),
        )

    def list_nodes(self) -> list[dict]:
        rows = get_database().query("SELECT * FROM nodes ORDER BY discovered_at DESC")
        return [self._node_row(r) for r in rows]

    def set_node_trust(self, node_id: str, trust: str) -> None:
        get_database().execute("UPDATE nodes SET trust = ? WHERE id = ?", (trust, node_id))

    def _node_row(self, r) -> dict:
        d = dict(r)
        d["manifest"] = json.loads(d["manifest"]) if d["manifest"] else {}
        return d

    # -- probing --------------------------------------------------------------

    async def probe_url(self, base_url: str) -> LCDPManifest | None:
        """Fetch /.well-known/lcdp.json (read-only). Returns manifest or None."""
        url = base_url.rstrip("/") + "/.well-known/lcdp.json"
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(url)
                r.raise_for_status()
                manifest = LCDPManifest.model_validate(r.json())
        except Exception:  # noqa: BLE001
            return None
        # Classify: Buster product → node, else generic service.
        if manifest.product == "buster":
            self.record_node(manifest)
        else:
            self.record_service(manifest)
        return manifest

    async def health_check_node(self, node_id: str) -> bool:
        row = get_database().query_one("SELECT manifest FROM nodes WHERE id = ?", (node_id,))
        if not row:
            return False
        manifest = json.loads(row["manifest"])
        health_url = manifest.get("health_url")
        if not health_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(health_url)
                return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False


@lru_cache(maxsize=1)
def get_discovery() -> DiscoveryRegistry:
    return DiscoveryRegistry()
