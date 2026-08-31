"""Repository layer for persisting triggers and managing bounded event history."""

from datetime import datetime, timezone
import json
from typing import Optional

from app.core.exceptions import StorageError, TriggerError
from app.core.logging import get_logger
from app.events.database import EventDatabase
from app.events.models import (
    EventHistoryRecord,
    EventType,
    Trigger,
    TriggerActionType,
    TriggerStatus,
)

logger = get_logger("events.repository")


class EventRepository:
    """Provides persistent CRUD operations for triggers and bounded event audit logging."""

    def __init__(self, db: Optional[EventDatabase] = None) -> None:
        self.db = db or EventDatabase()

    def _row_to_trigger(self, row: dict) -> Trigger:
        return Trigger(
            trigger_id=row["trigger_id"],
            name=row["name"],
            description=row["description"],
            event_type=EventType(row["event_type"]),
            conditions=json.loads(row["conditions_json"]),
            action_type=TriggerActionType(row["action_type"]),
            action_payload=json.loads(row["action_payload_json"]),
            status=TriggerStatus(row["status"]),
            cooldown_seconds=row["cooldown_seconds"],
            last_triggered_at=datetime.fromisoformat(row["last_triggered_at"]) if row["last_triggered_at"] else None,
            trigger_count=row["trigger_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_trigger(self, trigger: Trigger) -> Trigger:
        """Persist a new trigger."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO triggers (
                    trigger_id, name, description, event_type, conditions_json,
                    action_type, action_payload_json, status, cooldown_seconds,
                    last_triggered_at, trigger_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trigger.trigger_id,
                    trigger.name,
                    trigger.description,
                    trigger.event_type.value,
                    json.dumps(trigger.conditions),
                    trigger.action_type.value,
                    json.dumps(trigger.action_payload),
                    trigger.status.value,
                    trigger.cooldown_seconds,
                    trigger.last_triggered_at.isoformat() if trigger.last_triggered_at else None,
                    trigger.trigger_count,
                    trigger.created_at.isoformat(),
                    trigger.updated_at.isoformat(),
                ),
            )
        logger.info("Trigger '%s' (%s) persisted.", trigger.name, trigger.trigger_id)
        return trigger

    def get_trigger(self, trigger_id: str) -> Optional[Trigger]:
        """Fetch trigger by ID."""
        with self.db.transaction() as conn:
            cursor = conn.execute("SELECT * FROM triggers WHERE trigger_id = ?", (trigger_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_trigger(dict(row))
        return None

    def list_triggers(
        self,
        status: Optional[TriggerStatus] = None,
        event_type: Optional[EventType] = None,
    ) -> list[Trigger]:
        """List triggers with optional status and event_type filters."""
        triggers: list[Trigger] = []
        with self.db.transaction() as conn:
            query = "SELECT * FROM triggers WHERE 1=1"
            params = []
            if status:
                query += " AND status = ?"
                params.append(status.value)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type.value)
            query += " ORDER BY created_at DESC"

            cursor = conn.execute(query, tuple(params))
            for row in cursor.fetchall():
                triggers.append(self._row_to_trigger(dict(row)))
        return triggers

    def update_trigger(self, trigger: Trigger) -> Trigger:
        """Update trigger definition, status, or trigger counts."""
        trigger.updated_at = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE triggers SET
                    name = ?, description = ?, event_type = ?, conditions_json = ?,
                    action_type = ?, action_payload_json = ?, status = ?, cooldown_seconds = ?,
                    last_triggered_at = ?, trigger_count = ?, updated_at = ?
                WHERE trigger_id = ?
                """,
                (
                    trigger.name,
                    trigger.description,
                    trigger.event_type.value,
                    json.dumps(trigger.conditions),
                    trigger.action_type.value,
                    json.dumps(trigger.action_payload),
                    trigger.status.value,
                    trigger.cooldown_seconds,
                    trigger.last_triggered_at.isoformat() if trigger.last_triggered_at else None,
                    trigger.trigger_count,
                    trigger.updated_at.isoformat(),
                    trigger.trigger_id,
                ),
            )
            if cursor.rowcount == 0:
                raise TriggerError(f"Trigger '{trigger.trigger_id}' not found for update")
        return trigger

    def delete_trigger(self, trigger_id: str) -> bool:
        """Delete trigger by ID."""
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM triggers WHERE trigger_id = ?", (trigger_id,))
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted trigger '%s'.", trigger_id)
        return deleted

    def record_event(self, record: EventHistoryRecord, max_history: int = 100) -> None:
        """Log a processed event and enforce maximum history bound."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO event_history (
                    record_id, event_type, source, timestamp, summary, matched_triggers_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.event_type.value,
                    record.source,
                    record.timestamp.isoformat(),
                    record.summary[:500],
                    json.dumps(record.matched_triggers),
                ),
            )
            # Prune old records beyond max_history
            conn.execute(
                """
                DELETE FROM event_history WHERE record_id NOT IN (
                    SELECT record_id FROM event_history ORDER BY timestamp DESC LIMIT ?
                )
                """,
                (max_history,),
            )

    def get_recent_events(self, limit: int = 50) -> list[EventHistoryRecord]:
        """Fetch latest processed events."""
        records: list[EventHistoryRecord] = []
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM event_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            for r in cursor.fetchall():
                records.append(
                    EventHistoryRecord(
                        record_id=r["record_id"],
                        event_type=EventType(r["event_type"]),
                        source=r["source"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                        summary=r["summary"],
                        matched_triggers=json.loads(r["matched_triggers_json"]),
                    )
                )
        return records
