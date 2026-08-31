"""Task controller connecting persistent task manager and background scheduler to Qt GUI."""

from typing import Any, Optional
from PySide6.QtCore import QObject, Signal

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.tasks.manager import TaskManager
from app.tasks.models import Task, TaskExecution, TaskSchedule, TaskStatus, TaskType

logger = get_logger("ui.task_controller")


class TaskController(QObject):
    """Bridges TaskManager operations, scheduler notifications, and Qt UI event signals."""

    task_created = Signal(str)
    task_updated = Signal(str)
    task_notification = Signal(str, str, bool)  # title, message/result, success

    def __init__(
        self,
        task_manager: TaskManager,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.task_manager = task_manager
        self.settings = settings or get_settings()

        # Connect notification sink from manager
        self.task_manager.notification_sink = self._on_task_notification

    def _on_task_notification(self, task: Task, result: str, success: bool) -> None:
        """Callback invoked from background scheduler thread."""
        logger.info("Task notification emitted for '%s': success=%s", task.title, success)
        self.task_notification.emit(task.title, result, success)
        self.task_updated.emit(task.id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[Task]:
        return self.task_manager.list_tasks(status)

    def create_task(
        self,
        title: str,
        task_type: TaskType,
        schedule: TaskSchedule,
        prompt: str,
        description: Optional[str] = None,
    ) -> Task:
        task = self.task_manager.create_task(
            title=title,
            task_type=task_type,
            schedule=schedule,
            action_payload={"prompt": prompt},
            description=description,
        )
        self.task_created.emit(task.id)
        return task

    def pause_task(self, task_id: str) -> Task:
        task = self.task_manager.pause_task(task_id)
        self.task_updated.emit(task.id)
        return task

    def resume_task(self, task_id: str) -> Task:
        task = self.task_manager.resume_task(task_id)
        self.task_updated.emit(task.id)
        return task

    def cancel_task(self, task_id: str) -> Task:
        task = self.task_manager.cancel_task(task_id)
        self.task_updated.emit(task.id)
        return task

    def delete_task(self, task_id: str) -> bool:
        deleted = self.task_manager.delete_task(task_id)
        if deleted:
            self.task_updated.emit(task_id)
        return deleted

    def run_task_now(self, task_id: str) -> TaskExecution:
        exec_rec = self.task_manager.run_task_now(task_id)
        self.task_updated.emit(task_id)
        return exec_rec

    def get_task_executions(self, task_id: str) -> list[TaskExecution]:
        return self.task_manager.get_task_executions(task_id)
