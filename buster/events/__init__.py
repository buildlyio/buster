"""Structured event stream shared by CLI and web clients."""

from buster.events.bus import EventBus, get_event_bus
from buster.events.models import Event, EventType

__all__ = ["Event", "EventType", "EventBus", "get_event_bus"]
