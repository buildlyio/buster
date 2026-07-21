"""In-process async event bus with fan-out to subscribers + persistence.

Publishers call ``publish``. Subscribers (SSE endpoint, terminal renderer) get
their own bounded queue via ``subscribe``. Every event is also written to the
``task_events`` table so history survives restarts and both clients can replay.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from buster.database import get_database
from buster.events.models import Event


class EventBus:
    def __init__(self, max_queue: int = 512) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._max_queue = max_queue
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> None:
        self._persist(event)
        async with self._lock:
            dead: list[asyncio.Queue[Event]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)

    def publish_sync(self, event: Event) -> None:
        """Publish from non-async code (scheduler thread, etc.)."""
        self._persist(event)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop; persistence is enough
        loop.create_task(self.publish(event))

    def _persist(self, event: Event) -> None:
        db = get_database()
        db.execute(
            "INSERT INTO task_events (task_id, type, title, timestamp, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                event.task_id,
                event.type.value,
                event.title,
                event.timestamp,
                json.dumps(event.metadata),
            ),
        )

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue)
        async with self._lock:
            self._subscribers.add(q)
        try:
            yield q
        finally:
            async with self._lock:
                self._subscribers.discard(q)

    def recent(self, task_id: str | None = None, limit: int = 100) -> list[Event]:
        db = get_database()
        if task_id:
            rows = db.query(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY id DESC LIMIT ?",
                (task_id, limit),
            )
        else:
            rows = db.query(
                "SELECT * FROM task_events ORDER BY id DESC LIMIT ?", (limit,)
            )
        events = [
            Event(
                type=r["type"],
                timestamp=r["timestamp"],
                task_id=r["task_id"],
                title=r["title"],
                metadata=json.loads(r["payload"]),
            )
            for r in rows
        ]
        events.reverse()
        return events


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    return EventBus()
