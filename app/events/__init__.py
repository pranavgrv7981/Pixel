"""Background event engine and watcher automation package."""

from app.events.database import EventDatabase
from app.events.engine import EventEngine
from app.events.filters import EventDebouncer, EventRateLimiter, match_event_to_trigger
from app.events.models import (
    Event,
    EventHistoryRecord,
    EventOrigin,
    EventType,
    Trigger,
    TriggerActionType,
    TriggerStatus,
)
from app.events.repository import EventRepository
from app.events.watchers import ApplicationWatcher, FileWatcher, SystemMonitor

__all__ = [
    "ApplicationWatcher",
    "Event",
    "EventDatabase",
    "EventDebouncer",
    "EventEngine",
    "EventHistoryRecord",
    "EventOrigin",
    "EventRateLimiter",
    "EventRepository",
    "EventType",
    "FileWatcher",
    "SystemMonitor",
    "Trigger",
    "TriggerActionType",
    "TriggerStatus",
    "match_event_to_trigger",
]
