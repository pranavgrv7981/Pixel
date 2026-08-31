"""Unit tests for deterministic event condition matching, debouncing, and rate limiting."""

import time
from app.events.filters import EventDebouncer, EventRateLimiter, match_event_to_trigger
from app.events.models import Event, EventType, Trigger, TriggerActionType, TriggerStatus


def test_match_file_event_pattern() -> None:
    trigger = Trigger(
        name="PDF Trigger",
        event_type=EventType.FILE_CREATED,
        conditions={"pattern": "*.pdf"},
        action_type=TriggerActionType.NOTIFY_USER,
    )

    matching_event = Event(
        event_type=EventType.FILE_CREATED,
        payload={"path": "E:/AI AGENT/study.pdf", "filename": "study.pdf"},
    )
    non_matching_event = Event(
        event_type=EventType.FILE_CREATED,
        payload={"path": "E:/AI AGENT/notes.txt", "filename": "notes.txt"},
    )
    diff_type_event = Event(
        event_type=EventType.FILE_DELETED,
        payload={"path": "E:/AI AGENT/study.pdf", "filename": "study.pdf"},
    )

    assert match_event_to_trigger(matching_event, trigger) is True
    assert match_event_to_trigger(non_matching_event, trigger) is False
    assert match_event_to_trigger(diff_type_event, trigger) is False


def test_match_system_threshold_operators() -> None:
    trigger_gte = Trigger(
        name="RAM >= 90%",
        event_type=EventType.SYSTEM_THRESHOLD,
        conditions={"metric": "ram", "operator": ">=", "value": 90.0},
    )

    ev_high = Event(
        event_type=EventType.SYSTEM_THRESHOLD,
        payload={"metric": "ram", "value": 93.4},
    )
    ev_low = Event(
        event_type=EventType.SYSTEM_THRESHOLD,
        payload={"metric": "ram", "value": 75.0},
    )
    ev_diff_metric = Event(
        event_type=EventType.SYSTEM_THRESHOLD,
        payload={"metric": "cpu", "value": 95.0},
    )

    assert match_event_to_trigger(ev_high, trigger_gte) is True
    assert match_event_to_trigger(ev_low, trigger_gte) is False
    assert match_event_to_trigger(ev_diff_metric, trigger_gte) is False


def test_match_paused_trigger() -> None:
    trigger = Trigger(
        name="Paused Trigger",
        event_type=EventType.FILE_CREATED,
        conditions={"pattern": "*.pdf"},
        status=TriggerStatus.PAUSED,
    )
    ev = Event(
        event_type=EventType.FILE_CREATED,
        payload={"path": "E:/AI AGENT/study.pdf", "filename": "study.pdf"},
    )
    assert match_event_to_trigger(ev, trigger) is False


def test_event_debouncer_coalescing() -> None:
    debouncer = EventDebouncer(default_window_ms=200)
    ev = Event(
        event_type=EventType.FILE_MODIFIED,
        payload={"path": "E:/AI AGENT/output.log"},
    )

    # First event should pass
    assert debouncer.should_process(ev, window_ms=200) is True

    # Immediate second event should be debounced / blocked
    assert debouncer.should_process(ev, window_ms=200) is False

    # After 250ms sleep, next event should pass
    time.sleep(0.25)
    assert debouncer.should_process(ev, window_ms=200) is True


def test_event_rate_limiter() -> None:
    limiter = EventRateLimiter(max_per_second=5)

    # First 5 should succeed
    for _ in range(5):
        assert limiter.is_allowed() is True

    # 6th in same second should be blocked
    assert limiter.is_allowed() is False
