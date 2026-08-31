"""Event Engine coordinating background watchers, deterministic filters, triggers, and safe execution."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Callable, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import EventError, TriggerError
from app.core.logging import get_logger
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
from app.tools.path_guard import PathGuard

logger = get_logger("events.engine")


class EventEngine:
    """Central event orchestrator processing incoming watcher events and executing matched triggers."""

    def __init__(
        self,
        repository: Optional[EventRepository] = None,
        path_guard: Optional[PathGuard] = None,
        agent_executor: Optional[Callable[[str, bool], str]] = None,
        notification_sink: Optional[Callable[[str, str, str], None]] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or EventRepository()
        self.path_guard = path_guard or PathGuard(settings=self.settings)
        self.agent_executor = agent_executor
        self.notification_sink = notification_sink

        self.automation_enabled = self.settings.automation_enabled
        self.debouncer = EventDebouncer(default_window_ms=self.settings.file_watch_debounce_ms)
        self.rate_limiter = EventRateLimiter(max_per_second=self.settings.max_events_per_second)

        self._executor = ThreadPoolExecutor(
            max_workers=self.settings.max_concurrent_tasks,
            thread_name_prefix="EventWorker",
        )

        # Local Watchers
        self.file_watcher = FileWatcher(
            event_sink=self.ingest_event,
            path_guard=self.path_guard,
            settings=self.settings,
        )
        self.system_monitor = SystemMonitor(
            event_sink=self.ingest_event,
            poll_interval=self.settings.system_monitor_interval_seconds,
            settings=self.settings,
        )
        self.app_watcher = ApplicationWatcher(
            event_sink=self.ingest_event,
        )

        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def set_automation_enabled(self, enabled: bool) -> None:
        """Toggle master automation switch."""
        self.automation_enabled = enabled
        logger.info("Master automation switch updated: %s", "ENABLED" if enabled else "PAUSED")

    def start(self) -> None:
        """Start the background event engine and active watchers."""
        with self._lock:
            if self._running:
                return
            logger.info("Starting EventEngine (automation_enabled=%s)...", self.automation_enabled)
            self._running = True

            # Register allowed root directories into file watcher
            for root in self.settings.get_resolved_allowed_roots():
                try:
                    if root.is_dir():
                        self.file_watcher.add_watch_directory(root)
                except Exception as err:
                    logger.warning("Could not watch root %s: %s", root, err)

            self.file_watcher.start()
            self.system_monitor.start()
            self.app_watcher.start()
            logger.info("EventEngine and all local watchers started.")

    def stop(self) -> None:
        """Stop event watchers and background executor cleanly."""
        with self._lock:
            if not self._running:
                return
            logger.info("Stopping EventEngine...")
            self._running = False

        self.file_watcher.stop()
        self.system_monitor.stop()
        self.app_watcher.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
        logger.info("EventEngine stopped.")

    def ingest_event(self, event: Event) -> None:
        """Ingest, filter, debounce, and match an incoming event against registered triggers."""
        if not self.automation_enabled:
            logger.debug("Event %s dropped: automation is paused.", event.event_id)
            return

        if not self.rate_limiter.is_allowed():
            logger.warning("Event %s dropped due to rate limit.", event.event_id)
            return

        if not self.debouncer.should_process(event, window_ms=self.settings.file_watch_debounce_ms):
            return

        # Cascade Loop Protection: Drop agent-originated triggers that could loop
        if event.origin == EventOrigin.AGENT:
            logger.debug("Dropping agent-originated event to prevent cascade loops.")
            return

        # Fetch active triggers for this event type
        active_triggers = self.repository.list_triggers(
            status=TriggerStatus.ACTIVE,
            event_type=event.event_type,
        )

        matched_triggers: list[Trigger] = []
        now_utc = datetime.now(timezone.utc)

        for trigger in active_triggers:
            if trigger.is_in_cooldown(now_utc):
                logger.debug("Trigger '%s' matched but is in cooldown (skipping).", trigger.name)
                continue

            if match_event_to_trigger(event, trigger):
                matched_triggers.append(trigger)
                # Update trigger state
                trigger.last_triggered_at = now_utc
                trigger.trigger_count += 1
                self.repository.update_trigger(trigger)

        # Log event audit record
        summary = f"{event.event_type.value.upper()} from {event.source}"
        if event.payload.get("filename"):
            summary += f": {event.payload['filename']}"
        elif event.payload.get("metric"):
            summary += f": {event.payload['metric']}={event.payload.get('value')}"
        elif event.payload.get("application"):
            summary += f": {event.payload['application']}"

        record = EventHistoryRecord(
            event_type=event.event_type,
            source=event.source,
            timestamp=event.timestamp,
            summary=summary,
            matched_triggers=[t.name for t in matched_triggers],
        )
        self.repository.record_event(record, max_history=self.settings.max_event_history)

        # Dispatch matched trigger actions asynchronously
        for trigger in matched_triggers:
            self._executor.submit(self._execute_trigger_action, trigger, event)

    def _execute_trigger_action(self, trigger: Trigger, event: Event) -> None:
        """Execute a matched trigger action within safe autonomous boundaries."""
        logger.info("Executing trigger '%s' (action=%s)...", trigger.name, trigger.action_type.value)
        title = f"Automation: {trigger.name}"
        prompt = trigger.action_payload.get("prompt") or trigger.description or trigger.name

        try:
            if trigger.action_type == TriggerActionType.NOTIFY_USER:
                message = prompt
                if event.payload.get("filename"):
                    message = f"{prompt}\nDetected file: {event.payload['filename']}"
                elif event.payload.get("metric"):
                    message = f"{prompt}\nCurrent {event.payload['metric']}: {event.payload.get('value')}%"
                self._dispatch_notification(title, message, severity="info")

            elif trigger.action_type in (
                TriggerActionType.START_ASSISTANT_QUERY,
                TriggerActionType.RECALL_MEMORY,
                TriggerActionType.SEARCH_KNOWLEDGE,
                TriggerActionType.ASSISTANT_REMINDER,
            ):
                if self.agent_executor:
                    # Pass contextually safe prompt without arbitrary shell execution
                    event_context = f"[Background Event: {event.event_type.value}] {prompt}"
                    response = self.agent_executor(event_context, False)
                    self._dispatch_notification(title, response[:300], severity="info")
                else:
                    self._dispatch_notification(title, prompt, severity="info")

        except Exception as err:
            logger.error("Error executing trigger '%s': %s", trigger.name, err)
            self._dispatch_notification(title, f"Trigger failed: {err}", severity="error")

    def _dispatch_notification(self, title: str, message: str, severity: str = "info") -> None:
        """Forward notification to the UI and system tray."""
        if self.notification_sink:
            try:
                self.notification_sink(title, message, severity)
            except Exception as err:
                logger.warning("Error in notification sink: %s", err)
