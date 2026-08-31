"""Unit tests for EventDatabase schema initialization and EventRepository persistence."""

from pathlib import Path
import pytest

from app.events.database import EventDatabase
from app.events.models import (
    EventHistoryRecord,
    EventType,
    Trigger,
    TriggerActionType,
    TriggerStatus,
)
from app.events.repository import EventRepository


@pytest.fixture
def temp_event_repo(tmp_path: Path) -> EventRepository:
    db = EventDatabase(db_path=tmp_path / "test_events.db")
    return EventRepository(db=db)


def test_trigger_crud_lifecycle(temp_event_repo: EventRepository) -> None:
    trigger = Trigger(
        name="Study PDF Trigger",
        event_type=EventType.FILE_CREATED,
        conditions={"pattern": "*.pdf"},
        action_type=TriggerActionType.NOTIFY_USER,
        action_payload={"prompt": "Index study PDF"},
        cooldown_seconds=120,
    )

    # 1. Create
    created = temp_event_repo.create_trigger(trigger)
    assert created.trigger_id == trigger.trigger_id

    # 2. Get
    fetched = temp_event_repo.get_trigger(trigger.trigger_id)
    assert fetched is not None
    assert fetched.name == "Study PDF Trigger"
    assert fetched.conditions["pattern"] == "*.pdf"
    assert fetched.status == TriggerStatus.ACTIVE

    # 3. List
    active_list = temp_event_repo.list_triggers(status=TriggerStatus.ACTIVE)
    assert len(active_list) == 1
    assert active_list[0].trigger_id == trigger.trigger_id

    # 4. Update
    fetched.status = TriggerStatus.PAUSED
    fetched.trigger_count = 3
    temp_event_repo.update_trigger(fetched)

    updated = temp_event_repo.get_trigger(trigger.trigger_id)
    assert updated.status == TriggerStatus.PAUSED
    assert updated.trigger_count == 3

    # 5. Delete
    deleted = temp_event_repo.delete_trigger(trigger.trigger_id)
    assert deleted is True
    assert temp_event_repo.get_trigger(trigger.trigger_id) is None


def test_event_history_bounding(temp_event_repo: EventRepository) -> None:
    for i in range(15):
        rec = EventHistoryRecord(
            event_type=EventType.FILE_CREATED,
            source="file_watcher",
            summary=f"Event #{i}",
        )
        temp_event_repo.record_event(rec, max_history=10)

    recent = temp_event_repo.get_recent_events(limit=50)
    assert len(recent) == 10
    # Latest should be event 14
    assert recent[0].summary == "Event #14"
