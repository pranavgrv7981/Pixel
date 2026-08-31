"""Repository layer for persisting tasks, updating schedules, and logging execution history."""

from datetime import datetime, timezone
import json
from typing import Optional

from app.core.exceptions import StorageError, TaskNotFoundError
from app.core.logging import get_logger
from app.tasks.database import TaskDatabase
from app.tasks.models import (
    Task,
    TaskActionType,
    TaskExecution,
    TaskSchedule,
    TaskStatus,
    TaskType,
)

logger = get_logger("tasks.repository")


class TaskRepository:
    """Provides persistent CRUD operations and execution tracking for tasks."""

    def __init__(self, db: Optional[TaskDatabase] = None) -> None:
        self.db = db or TaskDatabase()

    def _row_to_task(self, row: dict) -> Task:
        schedule_data = json.loads(row["schedule_json"])
        if "exact_run_at_utc" in schedule_data and schedule_data["exact_run_at_utc"]:
            schedule_data["exact_run_at_utc"] = datetime.fromisoformat(schedule_data["exact_run_at_utc"])

        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            task_type=TaskType(row["task_type"]),
            status=TaskStatus(row["status"]),
            schedule=TaskSchedule(**schedule_data),
            action_type=TaskActionType(row["action_type"]),
            action_payload=json.loads(row["action_payload_json"]),
            timezone=row["timezone"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            next_run_at=datetime.fromisoformat(row["next_run_at"]) if row["next_run_at"] else None,
            last_run_at=datetime.fromisoformat(row["last_run_at"]) if row["last_run_at"] else None,
            run_count=row["run_count"],
            failure_count=row["failure_count"],
            max_runs=row["max_runs"],
        )

    def create_task(self, task: Task) -> Task:
        """Insert a new task into the database."""
        with self.db.transaction() as conn:
            sched_dict = task.schedule.model_dump()
            if sched_dict.get("exact_run_at_utc"):
                sched_dict["exact_run_at_utc"] = sched_dict["exact_run_at_utc"].isoformat()

            conn.execute(
                """
                INSERT INTO tasks (
                    id, title, description, task_type, status, schedule_json,
                    action_type, action_payload_json, timezone, created_at, updated_at,
                    next_run_at, last_run_at, run_count, failure_count, max_runs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.description,
                    task.task_type.value,
                    task.status.value,
                    json.dumps(sched_dict),
                    task.action_type.value,
                    json.dumps(task.action_payload),
                    task.timezone,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    task.next_run_at.isoformat() if task.next_run_at else None,
                    task.last_run_at.isoformat() if task.last_run_at else None,
                    task.run_count,
                    task.failure_count,
                    task.max_runs,
                ),
            )
        logger.info("Task '%s' (%s) created successfully.", task.title, task.id)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Fetch task by ID."""
        with self.db.transaction() as conn:
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_task(dict(row))
        return None

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[Task]:
        """List tasks optionally filtered by status, sorted by next run time."""
        tasks: list[Task] = []
        with self.db.transaction() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY next_run_at ASC NULLS LAST",
                    (status.value,),
                )
            else:
                cursor = conn.execute("SELECT * FROM tasks ORDER BY next_run_at ASC NULLS LAST")
            for row in cursor.fetchall():
                tasks.append(self._row_to_task(dict(row)))
        return tasks

    def update_task(self, task: Task) -> Task:
        """Update task fields and schedule."""
        task.updated_at = datetime.now(timezone.utc)
        sched_dict = task.schedule.model_dump()
        if sched_dict.get("exact_run_at_utc"):
            sched_dict["exact_run_at_utc"] = sched_dict["exact_run_at_utc"].isoformat()

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks SET
                    title = ?, description = ?, task_type = ?, status = ?, schedule_json = ?,
                    action_type = ?, action_payload_json = ?, timezone = ?, updated_at = ?,
                    next_run_at = ?, last_run_at = ?, run_count = ?, failure_count = ?, max_runs = ?
                WHERE id = ?
                """,
                (
                    task.title,
                    task.description,
                    task.task_type.value,
                    task.status.value,
                    json.dumps(sched_dict),
                    task.action_type.value,
                    json.dumps(task.action_payload),
                    task.timezone,
                    task.updated_at.isoformat(),
                    task.next_run_at.isoformat() if task.next_run_at else None,
                    task.last_run_at.isoformat() if task.last_run_at else None,
                    task.run_count,
                    task.failure_count,
                    task.max_runs,
                    task.id,
                ),
            )
            if cursor.rowcount == 0:
                raise TaskNotFoundError(f"Task with ID '{task.id}' does not exist")
        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete a task and its execution history."""
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted task ID '%s'.", task_id)
        return deleted

    def get_due_tasks(self, current_utc: datetime, limit: int = 50) -> list[Task]:
        """Fetch ACTIVE tasks whose next_run_at is <= current_utc."""
        if current_utc.tzinfo is None:
            current_utc = current_utc.replace(tzinfo=timezone.utc)
        tasks: list[Task] = []
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = ? AND next_run_at IS NOT NULL AND next_run_at <= ?
                ORDER BY next_run_at ASC
                LIMIT ?
                """,
                (TaskStatus.ACTIVE.value, current_utc.isoformat(), limit),
            )
            for row in cursor.fetchall():
                tasks.append(self._row_to_task(dict(row)))
        return tasks

    def has_occurrence_run(self, occurrence_id: str) -> bool:
        """Check if an occurrence ID has already been recorded/executed."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM task_executions WHERE occurrence_id = ?",
                (occurrence_id,),
            )
            return cursor.fetchone() is not None

    def record_execution_start(self, exec: TaskExecution) -> None:
        """Record the start of a task occurrence execution."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO task_executions (
                    execution_id, task_id, occurrence_id, started_at, completed_at,
                    status, result_summary, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exec.execution_id,
                    exec.task_id,
                    exec.occurrence_id,
                    exec.started_at.isoformat(),
                    exec.completed_at.isoformat() if exec.completed_at else None,
                    exec.status,
                    exec.result_summary,
                    exec.error_summary,
                ),
            )

    def record_execution_finish(self, exec: TaskExecution) -> None:
        """Update an execution record on completion."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE task_executions SET
                    completed_at = ?, status = ?, result_summary = ?, error_summary = ?
                WHERE execution_id = ?
                """,
                (
                    exec.completed_at.isoformat() if exec.completed_at else datetime.now(timezone.utc).isoformat(),
                    exec.status,
                    exec.result_summary,
                    exec.error_summary,
                    exec.execution_id,
                ),
            )

    def get_executions_for_task(self, task_id: str, limit: int = 20) -> list[TaskExecution]:
        """Fetch historical executions for a specific task."""
        executions: list[TaskExecution] = []
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM task_executions
                WHERE task_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (task_id, limit),
            )
            for r in cursor.fetchall():
                executions.append(
                    TaskExecution(
                        execution_id=r["execution_id"],
                        task_id=r["task_id"],
                        occurrence_id=r["occurrence_id"],
                        started_at=datetime.fromisoformat(r["started_at"]),
                        completed_at=datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None,
                        status=r["status"],
                        result_summary=r["result_summary"],
                        error_summary=r["error_summary"],
                    )
                )
        return executions
