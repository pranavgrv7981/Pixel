"""Schedule trigger evaluation and next run calculation utilities."""

from datetime import datetime, time as dtime, timedelta, timezone
import re
from typing import Optional

from app.core.exceptions import TaskValidationError
from app.tasks.models import TaskSchedule, TaskType


def compute_next_run(
    task_type: TaskType,
    schedule: TaskSchedule,
    after_utc: Optional[datetime] = None,
) -> Optional[datetime]:
    """Calculate the next execution timestamp in UTC strictly after `after_utc`."""
    now = after_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if task_type == TaskType.ONE_TIME:
        if schedule.exact_run_at_utc:
            exact = schedule.exact_run_at_utc
            if exact.tzinfo is None:
                exact = exact.replace(tzinfo=timezone.utc)
            return exact if exact > now else None
        return None

    if task_type == TaskType.INTERVAL:
        if not schedule.interval_seconds or schedule.interval_seconds <= 0:
            raise TaskValidationError("INTERVAL task requires positive 'interval_seconds'")
        return now + timedelta(seconds=schedule.interval_seconds)

    if task_type == TaskType.DAILY:
        if not schedule.daily_time_utc:
            raise TaskValidationError("DAILY task requires 'daily_time_utc' in 'HH:MM' format")
        try:
            parts = schedule.daily_time_utc.strip().split(":")
            hour, minute = int(parts[0]), int(parts[1])
            target_time = dtime(hour, minute, 0, tzinfo=timezone.utc)
        except Exception as err:
            raise TaskValidationError(f"Invalid 'daily_time_utc' '{schedule.daily_time_utc}': {err}") from err

        candidate = datetime.combine(now.date(), target_time)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if task_type == TaskType.WEEKLY:
        if schedule.weekly_day is None or schedule.weekly_day < 0 or schedule.weekly_day > 6:
            raise TaskValidationError("WEEKLY task requires 'weekly_day' between 0 (Monday) and 6 (Sunday)")
        if not schedule.weekly_time_utc:
            raise TaskValidationError("WEEKLY task requires 'weekly_time_utc' in 'HH:MM' format")
        try:
            parts = schedule.weekly_time_utc.strip().split(":")
            hour, minute = int(parts[0]), int(parts[1])
            target_time = dtime(hour, minute, 0, tzinfo=timezone.utc)
        except Exception as err:
            raise TaskValidationError(f"Invalid 'weekly_time_utc' '{schedule.weekly_time_utc}': {err}") from err

        # Find the next date with matching weekday
        days_ahead = (schedule.weekly_day - now.weekday()) % 7
        candidate_date = now.date() + timedelta(days=days_ahead)
        candidate = datetime.combine(candidate_date, target_time)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    return None


def parse_relative_time_expression(
    expr: str,
    base_time_utc: Optional[datetime] = None,
) -> Optional[datetime]:
    """Parse relative time expressions (e.g. 'in 10 minutes', 'in 2 hours', 'tomorrow at 18:00')."""
    if not expr or not expr.strip():
        return None

    clean = expr.strip().lower()
    base = base_time_utc or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    # 1. "in X seconds / minutes / hours / days"
    rel_match = re.match(r"(?:in\s+)?(\d+)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?|d|days?)$", clean)
    if rel_match:
        val = int(rel_match.group(1))
        unit = rel_match.group(2)
        if unit.startswith("s"):
            return base + timedelta(seconds=val)
        elif unit.startswith("m"):
            return base + timedelta(minutes=val)
        elif unit.startswith("h"):
            return base + timedelta(hours=val)
        elif unit.startswith("d"):
            return base + timedelta(days=val)

    # 2. "tomorrow at HH[:MM] [AM|PM]" or "today at HH[:MM] [AM|PM]"
    time_match = re.match(r"(today|tomorrow)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", clean)
    if time_match:
        day_str = time_match.group(1)
        hour = int(time_match.group(2))
        minute = int(time_match.group(3) or 0)
        ampm = time_match.group(4)

        if ampm:
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0

        target_date = base.date() + (timedelta(days=1) if day_str == "tomorrow" else timedelta(days=0))
        target = datetime.combine(target_date, dtime(hour, minute, 0, tzinfo=timezone.utc))
        if day_str == "today" and target <= base:
            target += timedelta(days=1)
        return target

    return None
