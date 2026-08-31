"""Tools for creating, listing, inspecting, and managing scheduled tasks."""

from typing import Any, Mapping, Optional
from pydantic import BaseModel, Field

from app.core.exceptions import TaskError, ToolValidationError
from app.tasks.manager import TaskManager
from app.tasks.models import TaskActionType, TaskSchedule, TaskStatus, TaskType
from app.tools.base import RiskLevel, Tool, ToolResult


class BaseTaskTool(Tool):
    """Base class for task management tools sharing a TaskManager reference."""

    def __init__(
        self,
        task_manager: TaskManager,
        name: str,
        description: str,
        risk_level: RiskLevel = RiskLevel.READ,
        args_model: Optional[type[BaseModel]] = None,
    ) -> None:
        super().__init__(name=name, description=description, risk_level=risk_level, args_model=args_model)
        self.task_manager = task_manager


class CreateTaskArgs(BaseModel):
    title: str = Field(description="Title or short name for the scheduled task")
    task_type: str = Field(
        default="one_time",
        description="Scheduling type: 'one_time', 'interval', 'daily', or 'weekly'",
    )
    prompt: str = Field(description="Action prompt or reminder content to execute")
    time_expression: Optional[str] = Field(
        default=None,
        description="Natural/relative time expression (e.g. 'in 10 minutes', 'tomorrow at 18:00')",
    )
    interval_seconds: Optional[int] = Field(
        default=None,
        description="Interval duration in seconds if task_type is 'interval'",
    )
    daily_time_utc: Optional[str] = Field(
        default=None,
        description="Daily execution time in 24h UTC (e.g. '08:00') if task_type is 'daily'",
    )
    weekly_day: Optional[int] = Field(
        default=None,
        description="Day of week (0=Monday, 6=Sunday) if task_type is 'weekly'",
    )
    weekly_time_utc: Optional[str] = Field(
        default=None,
        description="Weekly execution time in 24h UTC (e.g. '18:00') if task_type is 'weekly'",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional detailed description of the task",
    )


class CreateTaskTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="create_task",
            description="Create and schedule a new persistent task or reminder (one-time, interval, daily, or weekly).",
            risk_level=RiskLevel.MEDIUM,
            args_model=CreateTaskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        title = args.get("title", "").strip()
        task_type_str = args.get("task_type", "one_time").strip().lower()
        prompt = args.get("prompt", "").strip()
        time_expr = args.get("time_expression")
        desc = args.get("description")

        if time_expr and task_type_str == "one_time":
            task = self.task_manager.create_reminder(
                title=title,
                prompt=prompt,
                relative_or_exact_time=time_expr,
                description=desc,
            )
            return ToolResult(
                success=True,
                data={
                    "task_id": task.id,
                    "title": task.title,
                    "task_type": task.task_type.value,
                    "status": task.status.value,
                    "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                    "message": f"Scheduled reminder '{task.title}' for {task.next_run_at.isoformat() if task.next_run_at else 'soon'}",
                },
            )

        try:
            task_type = TaskType(task_type_str)
        except ValueError:
            raise ToolValidationError(f"Unsupported task_type '{task_type_str}'. Choose from: one_time, interval, daily, weekly")

        schedule = TaskSchedule(
            interval_seconds=args.get("interval_seconds"),
            daily_time_utc=args.get("daily_time_utc"),
            weekly_day=args.get("weekly_day"),
            weekly_time_utc=args.get("weekly_time_utc"),
        )

        task = self.task_manager.create_task(
            title=title,
            task_type=task_type,
            schedule=schedule,
            action_type=TaskActionType.ASSISTANT_REMINDER,
            action_payload={"prompt": prompt},
            description=desc,
        )

        return ToolResult(
            success=True,
            data={
                "task_id": task.id,
                "title": task.title,
                "task_type": task.task_type.value,
                "status": task.status.value,
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "message": f"Successfully created {task.task_type.value} task '{task.title}'",
            },
        )


class ListTasksArgs(BaseModel):
    status: Optional[str] = Field(
        default=None,
        description="Filter tasks by status: 'active', 'paused', 'completed', 'failed', 'cancelled'",
    )


class ListTasksTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="list_tasks",
            description="List all persistent scheduled tasks and reminders, optionally filtered by status.",
            risk_level=RiskLevel.READ,
            args_model=ListTasksArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        status_filter = None
        status_str = args.get("status")
        if status_str:
            status_filter = TaskStatus(status_str.strip().lower())

        summaries = self.task_manager.list_task_summaries(status_filter)
        return ToolResult(
            success=True,
            data={
                "count": len(summaries),
                "tasks": [s.model_dump() for s in summaries],
            },
        )


class GetTaskArgs(BaseModel):
    task_id: str = Field(description="Unique UUID identifier of the task")


class GetTaskTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="get_task",
            description="Retrieve detailed information, schedule parameters, and statistics for a specific task.",
            risk_level=RiskLevel.READ,
            args_model=GetTaskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        task = self.task_manager.get_task(task_id)
        return ToolResult(
            success=True,
            data={
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "task_type": task.task_type.value,
                "status": task.status.value,
                "schedule": task.schedule.model_dump(),
                "action_type": task.action_type.value,
                "action_payload": task.action_payload,
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
                "run_count": task.run_count,
                "failure_count": task.failure_count,
            },
        )


class PauseTaskTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="pause_task",
            description="Pause an active scheduled task so it will not trigger until resumed.",
            risk_level=RiskLevel.MEDIUM,
            args_model=GetTaskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        task = self.task_manager.pause_task(task_id)
        return ToolResult(
            success=True,
            data={"task_id": task.id, "title": task.title, "status": task.status.value, "message": "Task paused."},
        )


class ResumeTaskTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="resume_task",
            description="Resume a paused task and compute its next upcoming execution time.",
            risk_level=RiskLevel.MEDIUM,
            args_model=GetTaskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        task = self.task_manager.resume_task(task_id)
        return ToolResult(
            success=True,
            data={
                "task_id": task.id,
                "title": task.title,
                "status": task.status.value,
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "message": "Task resumed.",
            },
        )


class CancelTaskTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="cancel_task",
            description="Cancel a scheduled task permanently so it will no longer run.",
            risk_level=RiskLevel.MEDIUM,
            args_model=GetTaskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        task = self.task_manager.cancel_task(task_id)
        return ToolResult(
            success=True,
            data={"task_id": task.id, "title": task.title, "status": task.status.value, "message": "Task cancelled."},
        )


class DeleteTaskTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="delete_task",
            description="Permanently remove a task and its execution history from the database.",
            risk_level=RiskLevel.MEDIUM,
            args_model=GetTaskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        deleted = self.task_manager.delete_task(task_id)
        return ToolResult(
            success=deleted,
            data={"task_id": task_id, "deleted": deleted, "message": "Task permanently deleted." if deleted else "Task not found."},
        )


class RunTaskNowTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="run_task_now",
            description="Manually trigger immediate execution of a task without modifying its recurring schedule.",
            risk_level=RiskLevel.MEDIUM,
            args_model=GetTaskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        exec_rec = self.task_manager.run_task_now(task_id)
        return ToolResult(
            success=exec_rec.status == "success",
            data={
                "task_id": exec_rec.task_id,
                "execution_id": exec_rec.execution_id,
                "status": exec_rec.status,
                "result_summary": exec_rec.result_summary,
                "error_summary": exec_rec.error_summary,
            },
        )


class GetTaskExecutionsArgs(BaseModel):
    task_id: str = Field(description="Unique UUID identifier of the task")
    limit: int = Field(default=10, description="Maximum number of historical executions to return")


class GetTaskExecutionsTool(BaseTaskTool):
    def __init__(self, task_manager: TaskManager) -> None:
        super().__init__(
            task_manager=task_manager,
            name="get_task_executions",
            description="Retrieve recent execution history and status records for a specific task.",
            risk_level=RiskLevel.READ,
            args_model=GetTaskExecutionsArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        limit = int(args.get("limit", 10))
        executions = self.task_manager.get_task_executions(task_id, limit=limit)
        return ToolResult(
            success=True,
            data={
                "task_id": task_id,
                "count": len(executions),
                "executions": [e.model_dump() for e in executions],
            },
        )
