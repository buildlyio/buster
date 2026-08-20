"""Event→speech notifier.

Subscribes to the event bus and, for events in the user's announce list, speaks
a short phrase on this machine (TTS) AND emits a voice.announce event so an open
web/conversation page can speak it too (across the room). Respects the event
allowlist and quiet hours. Never announces its own voice.announce events.
"""

from __future__ import annotations

import asyncio
import contextlib

from buster.config import load_config
from buster.events import Event, EventType, get_event_bus

# Human phrasing per announced event type.
_PHRASES = {
    "runtime.task.completed": lambda e: f"Agent finished: {e.title or 'a task'}.",
    "runtime.task.failed": lambda e: f"An agent task failed: {e.title or ''}.",
    "research.report_updated": lambda e: f"Research is ready: {e.title or 'your report'}.",
    "action.verified": lambda e: f"Action verified: {e.title or ''}.",
    "alert.created": lambda e: f"Alert: {e.title or 'something needs attention'}.",
    "task.completed": lambda e: f"Done: {e.title or 'your task'}.",
}


def phrase_for(event: Event) -> str:
    fn = _PHRASES.get(event.type.value)
    return fn(event) if fn else (event.title or "")


class VoiceNotifier:
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
            with contextlib.suppress(Exception):
                await self._task

    async def _loop(self) -> None:
        bus = get_event_bus()
        async with bus.subscribe() as q:
            while not self._stop.is_set():
                try:
                    event = await asyncio.wait_for(q.get(), timeout=5.0)
                except TimeoutError:
                    continue
                await self._handle(event)

    async def _handle(self, event: Event) -> None:
        if event.type == EventType.VOICE_ANNOUNCE:
            return  # don't loop on our own announcements
        cfg = load_config().voice
        if not cfg.enabled:
            return
        if event.type.value not in cfg.announce_events:
            return
        text = phrase_for(event)
        if not text:
            return
        # Emit an announcement for any open web/conversation page.
        await get_event_bus().publish(Event(
            type=EventType.VOICE_ANNOUNCE, title=text,
            metadata={"source_event": event.type.value}))
        # Speak on this machine (in a thread; TTS is blocking).
        from buster.voice.speaker import get_speaker

        speaker = get_speaker()
        if speaker.available():
            await asyncio.to_thread(speaker.speak, text)
