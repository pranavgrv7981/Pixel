"""Deterministic event filtering, condition matching, debouncing, and rate limiting."""

from datetime import datetime, timezone
import fnmatch
from pathlib import Path
import threading
import time
from typing import Optional

from app.core.logging import get_logger
from app.events.models import Event, EventType, Trigger, TriggerStatus

logger = get_logger("events.filters")


def match_event_to_trigger(event: Event, trigger: Trigger) -> bool:
    """Evaluate whether an incoming event matches a trigger's configured conditions."""
    if trigger.status != TriggerStatus.ACTIVE:
        return False

    if event.event_type != trigger.event_type:
        return False

    conds = trigger.conditions or {}

    # 1. Filesystem Conditions
    if event.event_type in (EventType.FILE_CREATED, EventType.FILE_MODIFIED, EventType.FILE_DELETED):
        event_path_str = event.payload.get("path", "")
        if not event_path_str:
            return False
        event_path = Path(event_path_str)
        filename = event_path.name

        # Match path root or directory
        expected_dir = conds.get("path")
        if expected_dir:
            norm_expected = str(Path(expected_dir).resolve()).lower().rstrip("\\/")
            norm_event_path = str(event_path.resolve()).lower()
            if not (norm_event_path == norm_expected or norm_event_path.startswith(norm_expected + "\\") or norm_event_path.startswith(norm_expected + "/")):
                return False


        # Match glob pattern (e.g. *.pdf, *.txt)
        pattern = conds.get("pattern")
        if pattern and not fnmatch.fnmatch(filename.lower(), pattern.lower()):
            return False

        # Match extension (e.g. .pdf, pdf)
        ext = conds.get("extension")
        if ext:
            clean_ext = f".{ext.lstrip('.')}".lower()
            if event_path.suffix.lower() != clean_ext:
                return False

        return True

    # 2. System Threshold Conditions
    if event.event_type == EventType.SYSTEM_THRESHOLD:
        metric = conds.get("metric", "").lower()
        if metric and metric != event.payload.get("metric", "").lower():
            return False

        operator = conds.get("operator", ">=")
        target_val = conds.get("value")
        actual_val = event.payload.get("value")

        if target_val is not None and actual_val is not None:
            try:
                t_val = float(target_val)
                a_val = float(actual_val)
                if operator == ">=" and not (a_val >= t_val):
                    return False
                elif operator == ">" and not (a_val > t_val):
                    return False
                elif operator == "<=" and not (a_val <= t_val):
                    return False
                elif operator == "<" and not (a_val < t_val):
                    return False
                elif operator == "==" and not (abs(a_val - t_val) < 0.001):
                    return False
            except (ValueError, TypeError):
                return False

        return True

    # 3. Process / Application Lifecycle Conditions
    if event.event_type in (EventType.PROCESS_STARTED, EventType.PROCESS_STOPPED):
        app_name = conds.get("application", "").lower()
        event_app = event.payload.get("application", "").lower()
        if app_name and app_name not in event_app:
            return False
        return True

    # 4. Schedule Triggered Conditions
    if event.event_type == EventType.SCHEDULE_TRIGGERED:
        task_id = conds.get("task_id")
        if task_id and task_id != event.payload.get("task_id"):
            return False
        return True

    return True


class EventDebouncer:
    """Coalesces rapid duplicate events within a configurable millisecond window."""

    def __init__(self, default_window_ms: int = 500) -> None:
        self.default_window_ms = default_window_ms
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def should_process(self, event: Event, window_ms: Optional[int] = None) -> bool:
        """Return True if event is not a rapid duplicate within window_ms."""
        key = event.deduplication_key
        win = window_ms if window_ms is not None else self.default_window_ms
        now = time.time()

        with self._lock:
            last = self._last_seen.get(key, 0.0)
            elapsed_ms = (now - last) * 1000.0

            if elapsed_ms < win:
                logger.debug("Debounced event '%s' (elapsed=%.1fms < %dms)", key, elapsed_ms, win)
                return False

            self._last_seen[key] = now
            # Prune stale entries
            if len(self._last_seen) > 2000:
                cutoff = now - 3600.0
                self._last_seen = {k: v for k, v in self._last_seen.items() if v > cutoff}

            return True


class EventRateLimiter:
    """Enforces a maximum rate of processed events per second to prevent runaway floods."""

    def __init__(self, max_per_second: int = 20) -> None:
        self.max_per_second = max_per_second
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def is_allowed(self) -> bool:
        """Return True if within rate limit, False if threshold exceeded."""
        now = time.time()
        with self._lock:
            # Keep only timestamps within last 1.0s
            self._timestamps = [t for t in self._timestamps if (now - t) < 1.0]
            if len(self._timestamps) >= self.max_per_second:
                logger.warning("Event rate limit exceeded (%d events/s cap)", self.max_per_second)
                return False
            self._timestamps.append(now)
            return True
