"""Background task scheduler coordinating timed task triggers, concurrency limits, and occurrence lifecycle."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
import time
from typing import Callable, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import SchedulerError
from app.core.logging import get_logger
from app.tasks.models import (
    Task,
    TaskExecution,
    TaskExecutionContext,
    TaskStatus,
    TaskType,
)
from app.tasks.repository import TaskRepository
from app.tasks.triggers import compute_next_run

logger = get_logger("tasks.scheduler")


class TaskScheduler:
    """Manages scheduled background task evaluation, occurrence dispatching, and thread pools."""

    def __init__(
        self,
        repository: Optional[TaskRepository] = None,
        settings: Optional[Settings] = None,
        execution_handler: Optional[Callable[[Task, TaskExecutionContext], str]] = None,
        notification_handler: Optional[Callable[[Task, str, bool], None]] = None,
    ) -> None:
        self.repository = repository or TaskRepository()
        self.settings = settings or get_settings()
        self.execution_handler = execution_handler
        self.notification_handler = notification_handler

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=self.settings.max_concurrent_tasks,
            thread_name_prefix="TaskWorker",
        )
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the background scheduler thread."""
        with self._lock:
            if self._running:
                return
            if not self.settings.tasks_enabled:
                logger.info("TaskScheduler not started: tasks are disabled in configuration.")
                return

            logger.info("Starting TaskScheduler (poll_interval=%.1fs, max_concurrent=%d)...",
                        self.settings.task_scheduler_poll_seconds, self.settings.max_concurrent_tasks)

            self._reconcile_missed_tasks_on_startup()
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="TaskSchedulerThread", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Gracefully stop the background scheduler thread and active workers."""
        with self._lock:
            if not self._running:
                return
            logger.info("Stopping TaskScheduler...")
            self._running = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._executor.shutdown(wait=False, cancel_futures=True)
        logger.info("TaskScheduler stopped.")

    def _reconcile_missed_tasks_on_startup(self) -> None:
        """Apply missed-task policy for overdue tasks when the application starts."""
        now_utc = datetime.now(timezone.utc)
        overdue_tasks = self.repository.get_due_tasks(now_utc)
        if not overdue_tasks:
            return

        logger.info("Found %d overdue task(s) on startup. Policy: '%s'", len(overdue_tasks), self.settings.missed_task_policy)

        if self.settings.missed_task_policy == "skip":
            for task in overdue_tasks:
                if task.task_type == TaskType.ONE_TIME:
                    task.status = TaskStatus.COMPLETED
                    task.next_run_at = None
                else:
                    task.next_run_at = compute_next_run(task.task_type, task.schedule, after_utc=now_utc)
                self.repository.update_task(task)
                logger.info("Skipped overdue task '%s' -> next_run_at: %s", task.title, task.next_run_at)

    def _run_loop(self) -> None:
        """Main polling loop evaluating due tasks."""
        while self._running and not self._stop_event.is_set():
            try:
                self.poll_and_dispatch()
            except Exception as err:
                logger.exception("Unexpected error in scheduler poll loop: %s", err)

            self._stop_event.wait(self.settings.task_scheduler_poll_seconds)

    def poll_and_dispatch(self) -> list[Task]:
        """Check for due tasks and dispatch eligible ones to worker threads."""
        now_utc = datetime.now(timezone.utc)
        due_tasks = self.repository.get_due_tasks(now_utc, limit=self.settings.max_concurrent_tasks * 2)
        dispatched: list[Task] = []

        for task in due_tasks:
            if not self._running:
                break
            if task.next_run_at is None:
                continue

            scheduled_time = task.next_run_at
            occ_id = f"{task.id}_{scheduled_time.isoformat()}"

            # Deduplication check
            if self.repository.has_occurrence_run(occ_id):
                logger.debug("Occurrence '%s' already ran, skipping duplicate trigger.", occ_id)
                self._advance_task_schedule(task, scheduled_time)
                continue

            # Advance schedule in database immediately to prevent double-firing in next tick
            self._advance_task_schedule(task, scheduled_time)
            dispatched.append(task)

            # Submit task execution to worker pool
            self._executor.submit(self._worker_execute_task, task, occ_id, scheduled_time)

        return dispatched

    def _advance_task_schedule(self, task: Task, last_scheduled: datetime) -> None:
        """Update last run time and calculate next run time."""
        now_utc = datetime.now(timezone.utc)
        task.last_run_at = now_utc
        task.run_count += 1

        if task.task_type == TaskType.ONE_TIME:
            task.status = TaskStatus.COMPLETED
            task.next_run_at = None
        else:
            task.next_run_at = compute_next_run(task.task_type, task.schedule, after_utc=now_utc)
            if task.max_runs and task.run_count >= task.max_runs:
                task.status = TaskStatus.COMPLETED
                task.next_run_at = None

        self.repository.update_task(task)

    def _worker_execute_task(self, task: Task, occ_id: str, trigger_time: datetime) -> None:
        """Worker thread executing the action and recording execution history."""
        exec_record = TaskExecution(
            task_id=task.id,
            occurrence_id=occ_id,
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        self.repository.record_execution_start(exec_record)

        ctx = TaskExecutionContext(
            task_id=task.id,
            execution_id=exec_record.execution_id,
            trigger_time=trigger_time,
            source="scheduler",
            interactive=False,
        )

        logger.info("Executing scheduled task '%s' (occ_id=%s)...", task.title, occ_id)
        result_summary = ""
        success = True

        try:
            if self.execution_handler:
                result_summary = self.execution_handler(task, ctx)
            else:
                result_summary = f"Triggered action '{task.action_type.value}'"

            exec_record.status = "success"
            exec_record.result_summary = result_summary[:500]
            logger.info("Task '%s' completed successfully: %s", task.title, result_summary[:80])
        except Exception as err:
            success = False
            exec_record.status = "failed"
            exec_record.error_summary = str(err)[:500]
            task.failure_count += 1
            self.repository.update_task(task)
            logger.error("Task '%s' failed during execution: %s", task.title, err)
        finally:
            exec_record.completed_at = datetime.now(timezone.utc)
            self.repository.record_execution_finish(exec_record)

            if self.notification_handler:
                try:
                    self.notification_handler(task, result_summary or exec_record.error_summary or "", success)
                except Exception as err:
                    logger.warning("Error in task notification handler: %s", err)
