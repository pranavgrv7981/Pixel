"""Unit tests for Task models, schedules, and relative time parsing."""

from datetime import datetime, timezone
import pytest

from app.tasks.models import (
    Task,
    TaskActionType,
    TaskExecution,
    TaskSchedule,
    TaskStatus,
    TaskType,
)
from app.tasks.triggers import compute_next_run, parse_relative_time_expression


def test_parse_relative_time_expressions() -> None:
    base = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)

    # In 10 minutes
    t10m = parse_relative_time_expression("in 10 minutes", base_time_utc=base)
    assert t10m is not None
    assert (t10m - base).total_seconds() == 600

    # In 2 hours
    t2h = parse_relative_time_expression("in 2 hours", base_time_utc=base)
    assert t2h is not None
    assert (t2h - base).total_seconds() == 7200

    # Tomorrow at 19:00
    ttom = parse_relative_time_expression("tomorrow at 19:00", base_time_utc=base)
    assert ttom is not None
    assert ttom.day == 31
    assert ttom.hour == 19
    assert ttom.minute == 0


def test_compute_next_run_recurrences() -> None:
    base = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)

    # Interval
    sched_int = TaskSchedule(interval_seconds=3600)
    next_int = compute_next_run(TaskType.INTERVAL, sched_int, after_utc=base)
    assert next_int is not None
    assert (next_int - base).total_seconds() == 3600

    # Daily at 18:00
    sched_daily = TaskSchedule(daily_time_utc="18:00")
    next_daily = compute_next_run(TaskType.DAILY, sched_daily, after_utc=base)
    assert next_daily is not None
    assert next_daily.hour == 18
    assert next_daily.day == 30

    # Weekly Monday (day=0) at 09:00
    sched_weekly = TaskSchedule(weekly_day=0, weekly_time_utc="09:00")
    next_weekly = compute_next_run(TaskType.WEEKLY, sched_weekly, after_utc=base)
    assert next_weekly is not None
    assert next_weekly.weekday() == 0
    assert next_weekly.hour == 9
