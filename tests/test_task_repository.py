"""Unit tests for TaskRepository and TaskScheduler lifecycle."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import pytest

from app.core.config import Settings
from app.tasks.database import TaskDatabase
from app.tasks.models import (
    Task,
    TaskActionType,
    TaskSchedule,
    TaskStatus,
    TaskType,
)
from app.tasks.repository import TaskRepository
from app.tasks.scheduler import TaskScheduler


@pytest.fixture
def task_repo(tmp_path: Path) -> TaskRepository:
    db = TaskDatabase(db_path=tmp_path / "task_test.db")
    return TaskRepository(db=db)


def test_task_crud_and_due_tasks(task_repo: TaskRepository) -> None:
    now = datetime.now(timezone.utc)
    task = Task(
        id="task-123",
        title="Study Reminder",
        task_type=TaskType.ONE_TIME,
        schedule=TaskSchedule(exact_run_at_utc=now - timedelta(seconds=10)),
        action_type=TaskActionType.ASSISTANT_REMINDER,
        action_payload={"prompt": "Study AFL"},
        next_run_at=now - timedelta(seconds=10),
    )

    # Create
    task_repo.create_task(task)
    assert task_repo.get_task("task-123") is not None

    # Get due tasks
    due = task_repo.get_due_tasks(now)
    assert len(due) == 1
    assert due[0].id == "task-123"

    # Deduplication occurrence check
    occ_id = "task-123_occ1"
    assert task_repo.has_occurrence_run(occ_id) is False


def test_scheduler_poll_and_dispatch(task_repo: TaskRepository) -> None:
    executed_tasks: list[str] = []

    def handler(task: Task, ctx) -> str:
        executed_tasks.append(task.title)
        return "Done"

    scheduler = TaskScheduler(
        repository=task_repo,
        execution_handler=handler,
        settings=Settings(tasks_enabled=True, max_concurrent_tasks=2),
    )

    now = datetime.now(timezone.utc)
    task = Task(
        id="task-quick",
        title="Quick Reminder",
        task_type=TaskType.ONE_TIME,
        schedule=TaskSchedule(exact_run_at_utc=now - timedelta(seconds=5)),
        next_run_at=now - timedelta(seconds=5),
    )
    task_repo.create_task(task)

    scheduler._running = True
    dispatched = scheduler.poll_and_dispatch()

    assert len(dispatched) == 1
    assert dispatched[0].title == "Quick Reminder"

    time.sleep(0.2)
    assert "Quick Reminder" in executed_tasks
    scheduler.stop()
