"""SQLite access with WAL mode and a single controlled writer.

Reads use short-lived connections (WAL allows concurrent readers). Writes are
serialized through one lock so we never hit ``database is locked`` under the
in-process job queue. This keeps Buster lightweight — no separate DB server.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from buster.config.paths import get_paths
from buster.database.migrations import MIGRATIONS


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


class Database:
    """Thin SQLite wrapper. One writer connection, guarded by a lock."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._writer = _connect(path)
        self.migrate()

    # -- schema ---------------------------------------------------------------

    def migrate(self) -> int:
        """Apply outstanding migrations. Returns the resulting schema version."""
        with self._write_lock:
            cur = self._writer.execute("PRAGMA user_version")
            version = cur.fetchone()[0]
            for target, sql in MIGRATIONS:
                if target > version:
                    self._writer.executescript(sql)
                    self._writer.execute(f"PRAGMA user_version={target}")
                    version = target
            self._writer.commit()
            return version

    @property
    def schema_version(self) -> int:
        return self._writer.execute("PRAGMA user_version").fetchone()[0]

    # -- writes (serialized) --------------------------------------------------

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Run a write statement. Returns lastrowid."""
        with self._write_lock:
            cur = self._writer.execute(sql, tuple(params))
            self._writer.commit()
            return cur.lastrowid or 0

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        with self._write_lock:
            self._writer.executemany(sql, [tuple(p) for p in seq])
            self._writer.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialized multi-statement write transaction."""
        with self._write_lock:
            try:
                yield self._writer
                self._writer.commit()
            except Exception:
                self._writer.rollback()
                raise

    # -- reads (concurrent) ---------------------------------------------------

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        conn = _connect(self.path)
        try:
            return conn.execute(sql, tuple(params)).fetchall()
        finally:
            conn.close()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        conn = _connect(self.path)
        try:
            return conn.execute(sql, tuple(params)).fetchone()
        finally:
            conn.close()

    def close(self) -> None:
        self._writer.close()


@lru_cache(maxsize=1)
def get_database() -> Database:
    return Database(get_paths().db_file)
