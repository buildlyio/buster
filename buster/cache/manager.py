"""Cache manager with independently purgeable namespaces.

Layers:
  * in-memory: bounded LRU/TTL for hot values (context bundles, tool defs).
  * sqlite index: cache_entries table tracks keys, sizes, expiry, tags.
  * filesystem: large objects (fetched pages, extracted text) stored as files.

Clearing cache never removes durable memory, reports, tasks, prompt records,
user settings, or explicitly-saved research — those live outside the cache dir
and outside cache namespaces.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from datetime import UTC
from functools import lru_cache
from pathlib import Path
from typing import Any

from buster.config import get_paths, load_config
from buster.database import get_database

# Namespaces that are safe to purge.
NS_WEB = "web"                 # fetched pages / extracted text
NS_MODEL = "model_response"    # cached model responses (when safe)
NS_TEMP = "temp"               # scratch
NS_CONTEXT = "context"         # prepared context bundles


class _LRU:
    def __init__(self, max_items: int = 512) -> None:
        self._data: OrderedDict[str, tuple[float | None, Any]] = OrderedDict()
        self._max = max_items

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires is not None and expires < time.time():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: int | None) -> None:
        expires = time.time() + ttl if ttl else None
        self._data[key] = (expires, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


class CacheManager:
    def __init__(self) -> None:
        self._mem = _LRU()
        self._cfg = load_config()
        self._cache_dir = get_paths().cache_dir

    # -- in-memory ------------------------------------------------------------

    def mem_get(self, key: str) -> Any | None:
        return self._mem.get(key)

    def mem_set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._mem.set(key, value, ttl or self._cfg.cache.default_ttl_seconds)

    # -- persistent (sqlite index + optional file) ----------------------------

    def _now_iso(self) -> str:
        from datetime import datetime

        return datetime.now(UTC).astimezone().isoformat(timespec="seconds")

    def put(
        self,
        namespace: str,
        key: str,
        value: Any = None,
        *,
        content: bytes | None = None,
        ttl: int | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Store a value (JSON) and/or a binary object (file). Returns cache key."""
        db = get_database()
        full_key = f"{namespace}:{key}"
        file_path = None
        size = 0
        content_hash = ""
        if content is not None:
            content_hash = hashlib.sha256(content).hexdigest()
            ns_dir = self._cache_dir / namespace
            ns_dir.mkdir(parents=True, exist_ok=True)
            file_path = ns_dir / (content_hash + ".bin")
            file_path.write_bytes(content)
            size = len(content)
        value_json = json.dumps(value) if value is not None else None
        if value_json:
            size += len(value_json.encode())
        expires = None
        if ttl:
            from datetime import datetime, timedelta

            expires = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat()
        now = self._now_iso()
        db.execute(
            "INSERT INTO cache_entries (key, namespace, file_path, value, size_bytes, "
            "created_at, accessed_at, expires_at, content_hash, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, file_path=excluded.file_path, "
            "size_bytes=excluded.size_bytes, accessed_at=excluded.accessed_at, "
            "expires_at=excluded.expires_at, content_hash=excluded.content_hash, tags=excluded.tags",
            (
                full_key,
                namespace,
                str(file_path) if file_path else None,
                value_json,
                size,
                now,
                now,
                expires,
                content_hash,
                json.dumps(tags or []),
            ),
        )
        return full_key

    def get(self, namespace: str, key: str) -> dict | None:
        db = get_database()
        full_key = f"{namespace}:{key}"
        row = db.query_one("SELECT * FROM cache_entries WHERE key = ?", (full_key,))
        if not row:
            return None
        if row["expires_at"]:
            from datetime import datetime

            if datetime.fromisoformat(row["expires_at"]) < datetime.now(
                datetime.fromisoformat(row["expires_at"]).tzinfo
            ):
                self.delete(full_key)
                return None
        db.execute("UPDATE cache_entries SET accessed_at = ? WHERE key = ?", (self._now_iso(), full_key))
        out: dict[str, Any] = {"key": full_key}
        if row["value"]:
            out["value"] = json.loads(row["value"])
        if row["file_path"] and Path(row["file_path"]).exists():
            out["content"] = Path(row["file_path"]).read_bytes()
        return out

    def delete(self, full_key: str) -> None:
        db = get_database()
        row = db.query_one("SELECT file_path FROM cache_entries WHERE key = ?", (full_key,))
        if row and row["file_path"]:
            Path(row["file_path"]).unlink(missing_ok=True)
        db.execute("DELETE FROM cache_entries WHERE key = ?", (full_key,))

    # -- purge controls -------------------------------------------------------

    def clear_namespace(self, namespace: str) -> int:
        db = get_database()
        rows = db.query("SELECT key, file_path FROM cache_entries WHERE namespace = ?", (namespace,))
        for r in rows:
            if r["file_path"]:
                Path(r["file_path"]).unlink(missing_ok=True)
        db.execute("DELETE FROM cache_entries WHERE namespace = ?", (namespace,))
        if namespace in (NS_CONTEXT, NS_TEMP):
            self._mem.clear()
        return len(rows)

    def clear_expired(self) -> int:
        db = get_database()
        now = self._now_iso()
        rows = db.query(
            "SELECT key, file_path FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        for r in rows:
            if r["file_path"]:
                Path(r["file_path"]).unlink(missing_ok=True)
        db.execute("DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
        return len(rows)

    def clear_temp(self) -> int:
        return self.clear_namespace(NS_TEMP)

    def size_report(self) -> dict[str, Any]:
        db = get_database()
        rows = db.query(
            "SELECT namespace, COUNT(*) n, COALESCE(SUM(size_bytes),0) bytes "
            "FROM cache_entries GROUP BY namespace"
        )
        by_ns = {r["namespace"]: {"entries": r["n"], "bytes": r["bytes"]} for r in rows}
        total = sum(v["bytes"] for v in by_ns.values())
        return {"namespaces": by_ns, "total_bytes": total, "total_mb": round(total / 1024**2, 2)}

    def enforce_limits(self) -> int:
        """Evict least-recently-accessed entries if over the disk limit."""
        limit_bytes = self._cfg.cache.disk_limit_mb * 1024**2
        report = self.size_report()
        if report["total_bytes"] <= limit_bytes:
            return 0
        db = get_database()
        rows = db.query("SELECT key, file_path, size_bytes FROM cache_entries ORDER BY accessed_at ASC")
        freed = 0
        total = report["total_bytes"]
        removed = 0
        for r in rows:
            if total <= limit_bytes:
                break
            if r["file_path"]:
                Path(r["file_path"]).unlink(missing_ok=True)
            db.execute("DELETE FROM cache_entries WHERE key = ?", (r["key"],))
            total -= r["size_bytes"]
            freed += r["size_bytes"]
            removed += 1
        return removed


@lru_cache(maxsize=1)
def get_cache() -> CacheManager:
    return CacheManager()
