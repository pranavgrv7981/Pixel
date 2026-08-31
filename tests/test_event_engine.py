"""Unit tests for EventEngine event routing, master switch, loop prevention, and trigger execution."""

from pathlib import Path
import time
from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.events.database import EventDatabase
from app.events.engine import EventEngine
from app.events.models import (
    Event,
    EventOrigin,
    EventType,
    Trigger,
    TriggerActionType,
    TriggerStatus,
)
from app.events.repository import EventRepository
from app.tools.path_guard import PathGuard


@pytest.fixture
def test_engine(tmp_path: Path) -> EventEngine:
    db = EventDatabase(db_path=tmp_path / "engine_test.db")
    repo = EventRepository(db=db)
    guard = PathGuard(allowed_roots=[tmp_path])
    return EventEngine(repository=repo, path_guard=guard)



def test_engine_dispatches_matching_trigger_to_notification(test_engine: EventEngine) -> None:
    notifications: list[tuple[str, str, str]] = []
    test_engine.notification_sink = lambda t, m, s: notifications.append((t, m, s))

    # Register trigger
    trig = Trigger(
        name="PDF Detector",
        event_type=EventType.FILE_CREATED,
        conditions={"pattern": "*.pdf"},
        action_type=TriggerActionType.NOTIFY_USER,
        action_payload={"prompt": "New PDF detected"},
        cooldown_seconds=10,
    )
    test_engine.repository.create_trigger(trig)

    # Ingest matching event
    ev = Event(
        event_type=EventType.FILE_CREATED,
        origin=EventOrigin.WATCHER,
        source="file_watcher",
        payload={"path": "E:/AI AGENT/doc.pdf", "filename": "doc.pdf"},
    )
    test_engine.ingest_event(ev)

    time.sleep(0.1)
    assert len(notifications) == 1
    assert "Automation: PDF Detector" in notifications[0][0]
    assert "doc.pdf" in notifications[0][1]


def test_engine_master_automation_pause(test_engine: EventEngine) -> None:
    notifications: list = []
    test_engine.notification_sink = lambda t, m, s: notifications.append((t, m, s))

    trig = Trigger(
        name="Alert Trigger",
        event_type=EventType.SYSTEM_THRESHOLD,
        conditions={"metric": "ram"},
        action_type=TriggerActionType.NOTIFY_USER,
    )
    test_engine.repository.create_trigger(trig)

    # Pause master switch
    test_engine.set_automation_enabled(False)

    ev = Event(
        event_type=EventType.SYSTEM_THRESHOLD,
        payload={"metric": "ram", "value": 95.0},
    )
    test_engine.ingest_event(ev)

    time.sleep(0.1)
    # Event should have been dropped
    assert len(notifications) == 0


def test_engine_loop_prevention_agent_origin(test_engine: EventEngine) -> None:
    notifications: list = []
    test_engine.notification_sink = lambda t, m, s: notifications.append((t, m, s))

    trig = Trigger(
        name="Self Loop Guard",
        event_type=EventType.FILE_CREATED,
        conditions={"pattern": "*.txt"},
        action_type=TriggerActionType.NOTIFY_USER,
    )
    test_engine.repository.create_trigger(trig)

    # Event originated by AGENT tool execution
    agent_ev = Event(
        event_type=EventType.FILE_CREATED,
        origin=EventOrigin.AGENT,
        source="agent_tool",
        payload={"path": "E:/AI AGENT/generated.txt", "filename": "generated.txt"},
    )
    test_engine.ingest_event(agent_ev)

    time.sleep(0.1)
    assert len(notifications) == 0
