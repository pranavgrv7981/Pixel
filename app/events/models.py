"""Event and Trigger models for real-time background automation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Supported real-time and scheduled event categories."""
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    PROCESS_STARTED = "process_started"
    PROCESS_STOPPED = "process_stopped"
    SYSTEM_THRESHOLD = "system_threshold"
    SCHEDULE_TRIGGERED = "schedule_triggered"


class EventOrigin(str, Enum):
    """Originator of the event (used for cascade loop protection)."""
    USER = "user"
    SYSTEM = "system"
    SCHEDULE = "schedule"
    WATCHER = "watcher"
    AGENT = "agent"


class TriggerStatus(str, Enum):
    """Lifecycle status of a background event trigger."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    EXPIRED = "expired"


class TriggerActionType(str, Enum):
    """Controlled, whitelisted action types that background triggers may invoke."""
    NOTIFY_USER = "notify_user"
    START_ASSISTANT_QUERY = "start_assistant_query"
    RECALL_MEMORY = "recall_memory"
    SEARCH_KNOWLEDGE = "search_knowledge"
    ASSISTANT_REMINDER = "assistant_reminder"


class Event(BaseModel):
    """Discrete real-time or scheduled event representation."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    origin: EventOrigin = EventOrigin.WATCHER
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "watcher"
    payload: dict[str, Any] = Field(default_factory=dict)
    processed: bool = False

    @property
    def deduplication_key(self) -> str:
        """Key used for debouncing/coalescing rapid events."""
        if self.event_type in (EventType.FILE_CREATED, EventType.FILE_MODIFIED, EventType.FILE_DELETED):
            path = self.payload.get("path", "")
            return f"{self.event_type.value}:{path}"
        if self.event_type == EventType.SYSTEM_THRESHOLD:
            metric = self.payload.get("metric", "")
            return f"threshold:{metric}"
        if self.event_type in (EventType.PROCESS_STARTED, EventType.PROCESS_STOPPED):
            app_name = self.payload.get("application", "")
            return f"{self.event_type.value}:{app_name}"
        return f"{self.event_type.value}:{self.event_id}"


class Trigger(BaseModel):
    """Configured rule mapping matching events to controlled assistant actions."""
    trigger_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    event_type: EventType
    conditions: dict[str, Any] = Field(default_factory=dict)
    action_type: TriggerActionType = TriggerActionType.NOTIFY_USER
    action_payload: dict[str, Any] = Field(default_factory=dict)
    status: TriggerStatus = TriggerStatus.ACTIVE
    cooldown_seconds: int = 300
    last_triggered_at: Optional[datetime] = None
    trigger_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_in_cooldown(self, now_utc: Optional[datetime] = None) -> bool:
        """Check if trigger is currently within its cooldown window."""
        if self.last_triggered_at is None:
            return False
        now = now_utc or datetime.now(timezone.utc)
        elapsed = (now - self.last_triggered_at).total_seconds()
        return elapsed < self.cooldown_seconds


class EventHistoryRecord(BaseModel):
    """Historical audit record for a processed background event."""
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    source: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str
    matched_triggers: list[str] = Field(default_factory=list)
