"""Task Manager coordinating persistence, scheduler lifecycle, and Agent action execution."""

from datetime import datetime, timezone
from typing import Any, Callable, Optional
import uuid

from app.core.config import Settings, get_settings
from app.core.exceptions import TaskError, TaskNotFoundError, TaskValidationError
from app.core.logging import get_logger
from app.tasks.models import (
    Task,
    TaskActionType,
    TaskExecution,
    TaskExecutionContext,
    TaskSchedule,
    TaskStatus,
    TaskSummary,
    TaskType,
)
from app.tasks.repository import TaskRepository
from app.tasks.scheduler import TaskScheduler
from app.tasks.security import validate_task_action
from app.tasks.triggers import compute_next_run, parse_relative_time_expression

logger = get_logger("tasks.manager")


class TaskManager:
    """Central manager governing task creation, lifecycle transitions, and scheduled execution."""

    def __init__(
        self,
        repository: Optional[TaskRepository] = None,
        scheduler: Optional[TaskScheduler] = None,
        agent_executor: Optional[Callable[[str, bool], str]] = None,
        notification_sink: Optional[Callable[[Task, str, bool], None]] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or TaskRepository()
        self.agent_executor = agent_executor
        self.notification_sink = notification_sink

        self.scheduler = scheduler or TaskScheduler(
            repository=self.repository,
            settings=self.settings,
            execution_handler=self._handle_task_execution,
            notification_handler=self._handle_task_notification,
        )

        if self.settings.tasks_enabled:
            self.scheduler.start()

    def create_task(
        self,
        title: str,
        task_type: TaskType,
        schedule: TaskSchedule,
        action_type: TaskActionType = TaskActionType.ASSISTANT_REMINDER,
        action_payload: Optional[dict[str, Any]] = None,
        description: Optional[str] = None,
        timezone_name: str = "UTC",
        max_runs: Optional[int] = None,
    ) -> Task:
        """Create and persist a new validated scheduled task."""
        if not title or not title.strip():
            raise TaskValidationError("Task title cannot be empty")

        payload = action_payload or {}
        validate_task_action(action_type, payload)

        now_utc = datetime.now(timezone.utc)
        next_run = compute_next_run(task_type, schedule, after_utc=now_utc)
        if next_run is None:
            raise TaskValidationError(f"Could not calculate a valid future next run for task '{title}'")

        task = Task(
            id=str(uuid.uuid4()),
            title=title.strip(),
            description=description.strip() if description else None,
            task_type=task_type,
            status=TaskStatus.ACTIVE,
            schedule=schedule,
            action_type=action_type,
            action_payload=payload,
            timezone=timezone_name,
            created_at=now_utc,
            updated_at=now_utc,
            next_run_at=next_run,
            max_runs=max_runs,
        )

        return self.repository.create_task(task)

    def create_reminder(
        self,
        title: str,
        prompt: str,
        relative_or_exact_time: str,
        description: Optional[str] = None,
    ) -> Task:
        """Helper to create a one-time reminder from relative or exact time expression."""
        now_utc = datetime.now(timezone.utc)
        run_at = parse_relative_time_expression(relative_or_exact_time, base_time_utc=now_utc)

        if run_at is None:
            try:
                run_at = datetime.fromisoformat(relative_or_exact_time)
                if run_at.tzinfo is None:
                    run_at = run_at.replace(tzinfo=timezone.utc)
            except Exception as err:
                raise TaskValidationError(f"Could not parse reminder time '{relative_or_exact_time}': {err}") from err

        if run_at <= now_utc:
            raise TaskValidationError(f"Reminder time '{run_at.isoformat()}' must be in the future")

        schedule = TaskSchedule(exact_run_at_utc=run_at)
        return self.create_task(
            title=title,
            task_type=TaskType.ONE_TIME,
            schedule=schedule,
            action_type=TaskActionType.ASSISTANT_REMINDER,
            action_payload={"prompt": prompt},
            description=description,
        )

    def get_task(self, task_id: str) -> Task:
        """Retrieve task by ID or raise TaskNotFoundError."""
        task = self.repository.get_task(task_id)
        if not task:
            raise TaskNotFoundError(f"Task with ID '{task_id}' not found")
        return task

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[Task]:
        """List tasks optionally filtered by status."""
        return self.repository.list_tasks(status)

    def list_task_summaries(self, status: Optional[TaskStatus] = None) -> list[TaskSummary]:
        """Return concise summaries of tasks."""
        tasks = self.list_tasks(status)
        return [
            TaskSummary(
                id=t.id,
                title=t.title,
                task_type=t.task_type,
                status=t.status,
                next_run_at=t.next_run_at.isoformat() if t.next_run_at else None,
                last_run_at=t.last_run_at.isoformat() if t.last_run_at else None,
                run_count=t.run_count,
                failure_count=t.failure_count,
            )
            for t in tasks
        ]

    def pause_task(self, task_id: str) -> Task:
        """Pause an active scheduled task."""
        task = self.get_task(task_id)
        if task.status != TaskStatus.ACTIVE:
            raise TaskValidationError(f"Cannot pause task '{task.title}' in state '{task.status.value}'")

        task.status = TaskStatus.PAUSED
        task.next_run_at = None
        return self.repository.update_task(task)

    def resume_task(self, task_id: str) -> Task:
        """Resume a paused scheduled task."""
        task = self.get_task(task_id)
        if task.status != TaskStatus.PAUSED:
            raise TaskValidationError(f"Cannot resume task '{task.title}' in state '{task.status.value}'")

        now_utc = datetime.now(timezone.utc)
        next_run = compute_next_run(task.task_type, task.schedule, after_utc=now_utc)
        if next_run is None and task.task_type == TaskType.ONE_TIME:
            raise TaskValidationError(f"One-time task '{task.title}' cannot be resumed as its execution time has passed")

        task.status = TaskStatus.ACTIVE
        task.next_run_at = next_run
        return self.repository.update_task(task)

    def cancel_task(self, task_id: str) -> Task:
        """Cancel a task."""
        task = self.get_task(task_id)
        task.status = TaskStatus.CANCELLED
        task.next_run_at = None
        return self.repository.update_task(task)

    def delete_task(self, task_id: str) -> bool:
        """Permanently delete a task."""
        return self.repository.delete_task(task_id)

    def run_task_now(self, task_id: str) -> TaskExecution:
        """Manually trigger immediate execution of a task without breaking normal recurrence."""
        task = self.get_task(task_id)
        now_utc = datetime.now(timezone.utc)
        occ_id = f"manual_{task.id}_{now_utc.isoformat()}"

        exec_record = TaskExecution(
            task_id=task.id,
            occurrence_id=occ_id,
            started_at=now_utc,
            status="running",
        )
        self.repository.record_execution_start(exec_record)

        ctx = TaskExecutionContext(
            task_id=task.id,
            execution_id=exec_record.execution_id,
            trigger_time=now_utc,
            source="manual_run",
            interactive=False,
        )

        try:
            result = self._handle_task_execution(task, ctx)
            exec_record.status = "success"
            exec_record.result_summary = result[:500]
            task.last_run_at = now_utc
            task.run_count += 1
            self.repository.update_task(task)
            self._handle_task_notification(task, result, True)
        except Exception as err:
            exec_record.status = "failed"
            exec_record.error_summary = str(err)[:500]
            task.failure_count += 1
            self.repository.update_task(task)
            self._handle_task_notification(task, str(err), False)
        finally:
            exec_record.completed_at = datetime.now(timezone.utc)
            self.repository.record_execution_finish(exec_record)

        return exec_record

    def get_task_executions(self, task_id: str, limit: int = 20) -> list[TaskExecution]:
        """Fetch historical executions for a task."""
        self.get_task(task_id)
        return self.repository.get_executions_for_task(task_id, limit)

    def _handle_task_execution(self, task: Task, ctx: TaskExecutionContext) -> str:
        """Route scheduled task action through the Agent executor."""
        prompt = task.action_payload.get("prompt") or task.action_payload.get("message") or task.title

        if task.action_type == TaskActionType.ASSISTANT_REMINDER:
            # Simple reminders do not need full agent reasoning unless configured
            return f"🔔 Reminder: {prompt}"

        if self.agent_executor:
            # Run prompt through Agent non-interactively
            return self.agent_executor(prompt, False)

        return f"Processed task '{task.title}' ({task.action_type.value})"

    def _handle_task_notification(self, task: Task, result: str, success: bool) -> None:
        """Dispatch notification to registered sink (e.g. GUI / Status)."""
        if self.notification_sink:
            try:
                self.notification_sink(task, result, success)
            except Exception as err:
                logger.warning("Notification sink error: %s", err)

    def shutdown(self) -> None:
        """Cleanly stop scheduler on application exit."""
        logger.info("TaskManager shutting down...")
        self.scheduler.stop()
