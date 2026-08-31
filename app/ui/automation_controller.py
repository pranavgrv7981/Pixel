"""Automation controller coordinating EventEngine, TaskManager, and Qt event signals."""

from typing import Any, Optional
from PySide6.QtCore import QObject, Signal

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.events.engine import EventEngine
from app.events.models import EventHistoryRecord, Trigger, TriggerStatus
from app.tasks.manager import TaskManager

logger = get_logger("ui.automation_controller")


class AutomationController(QObject):
    """Bridges EventEngine background activity, triggers, and Qt UI event signals."""

    automation_mode_changed = Signal(bool)
    trigger_created = Signal(str)
    trigger_updated = Signal(str)
    event_notification = Signal(str, str, str)  # title, message, severity

    def __init__(
        self,
        event_engine: EventEngine,
        task_manager: Optional[TaskManager] = None,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.event_engine = event_engine
        self.task_manager = task_manager
        self.settings = settings or get_settings()

        # Connect event notification sink
        self.event_engine.notification_sink = self._on_engine_notification

    def _on_engine_notification(self, title: str, message: str, severity: str) -> None:
        """Callback invoked from background worker threads."""
        logger.info("Automation event notification: '%s'", title)
        self.event_notification.emit(title, message, severity)

    def is_automation_enabled(self) -> bool:
        return self.event_engine.automation_enabled

    def set_automation_enabled(self, enabled: bool) -> None:
        self.event_engine.set_automation_enabled(enabled)
        self.automation_mode_changed.emit(enabled)

    def list_triggers(self, status: Optional[TriggerStatus] = None) -> list[Trigger]:
        return self.event_engine.repository.list_triggers(status=status)

    def pause_trigger(self, trigger_id: str) -> Trigger:
        trigger = self.event_engine.repository.get_trigger(trigger_id)
        if trigger:
            trigger.status = TriggerStatus.PAUSED
            self.event_engine.repository.update_trigger(trigger)
            self.trigger_updated.emit(trigger_id)
        return trigger

    def resume_trigger(self, trigger_id: str) -> Trigger:
        trigger = self.event_engine.repository.get_trigger(trigger_id)
        if trigger:
            trigger.status = TriggerStatus.ACTIVE
            self.event_engine.repository.update_trigger(trigger)
            self.trigger_updated.emit(trigger_id)
        return trigger

    def delete_trigger(self, trigger_id: str) -> bool:
        deleted = self.event_engine.repository.delete_trigger(trigger_id)
        if deleted:
            self.trigger_updated.emit(trigger_id)
        return deleted

    def get_recent_events(self, limit: int = 50) -> list[EventHistoryRecord]:
        return self.event_engine.repository.get_recent_events(limit=limit)
