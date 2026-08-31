"""Unit tests for Event and Trigger domain models and enums."""

from datetime import datetime, timedelta, timezone
from app.events.models import (
    Event,
    EventHistoryRecord,
    EventOrigin,
    EventType,
    Trigger,
    TriggerActionType,
    TriggerStatus,
)


def test_event_creation_and_defaults() -> None:
    event = Event(
        event_type=EventType.FILE_CREATED,
        source="file_watcher",
        payload={"path": "E:/AI AGENT/test.pdf", "filename": "test.pdf"},
    )
    assert event.event_type == EventType.FILE_CREATED
    assert event.origin == EventOrigin.WATCHER
    assert event.source == "file_watcher"
    assert event.payload["filename"] == "test.pdf"
    assert event.processed is False
    assert event.event_id is not None
    assert isinstance(event.timestamp, datetime)


def test_event_deduplication_keys() -> None:
    file_ev = Event(
        event_type=EventType.FILE_CREATED,
        payload={"path": "E:/AI AGENT/doc.pdf"},
    )
    assert file_ev.deduplication_key == "file_created:E:/AI AGENT/doc.pdf"

    thresh_ev = Event(
        event_type=EventType.SYSTEM_THRESHOLD,
        payload={"metric": "ram", "value": 92.5},
    )
    assert thresh_ev.deduplication_key == "threshold:ram"

    proc_ev = Event(
        event_type=EventType.PROCESS_STARTED,
        payload={"application": "code"},
    )
    assert proc_ev.deduplication_key == "process_started:code"


def test_trigger_cooldown_evaluation() -> None:
    now = datetime.now(timezone.utc)
    trigger = Trigger(
        name="High RAM Alert",
        event_type=EventType.SYSTEM_THRESHOLD,
        conditions={"metric": "ram", "operator": ">=", "value": 90.0},
        action_type=TriggerActionType.NOTIFY_USER,
        cooldown_seconds=300,
        last_triggered_at=now - timedelta(seconds=100),
    )
    # Elapsed 100s < 300s -> in cooldown
    assert trigger.is_in_cooldown(now) is True

    # After 350s -> outside cooldown
    assert trigger.is_in_cooldown(now + timedelta(seconds=250)) is False


def test_event_history_record() -> None:
    rec = EventHistoryRecord(
        event_type=EventType.FILE_CREATED,
        source="file_watcher",
        summary="FILE_CREATED: test.pdf",
        matched_triggers=["New PDF trigger"],
    )
    assert rec.summary == "FILE_CREATED: test.pdf"
    assert "New PDF trigger" in rec.matched_triggers
