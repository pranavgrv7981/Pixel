"""Qt Controller coordinating multi-step planning, background worker execution, and UI signals."""

import threading
from typing import Optional
from PySide6.QtCore import QObject, Signal

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.planning.executor import PlanExecutor
from app.planning.models import Plan, PlanStep
from app.planning.planner import Planner
from app.planning.repository import PlanRepository

logger = get_logger("ui.plan_controller")


class PlanController(QObject):
    """Bridges plan generation and execution threads with Qt main UI thread."""

    # UI Signals
    plan_generated = Signal(object)  # Plan
    plan_started = Signal(object)  # Plan
    step_started = Signal(object, object)  # Plan, PlanStep
    step_completed = Signal(object, object)  # Plan, PlanStep
    step_failed = Signal(object, object, str)  # Plan, PlanStep, error
    plan_paused = Signal(object)  # Plan
    plan_resumed = Signal(object)  # Plan
    plan_completed = Signal(object)  # Plan
    plan_failed = Signal(object, str)  # Plan, error
    plan_cancelled = Signal(object)  # Plan
    plan_notification = Signal(str, str, str)  # title, message, severity

    def __init__(
        self,
        planner: Planner,
        executor: PlanExecutor,
        repository: PlanRepository,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.planner = planner
        self.executor = executor
        self.repository = repository
        self.settings = settings or get_settings()

        self._active_plan: Optional[Plan] = None
        self._execution_thread: Optional[threading.Thread] = None

        # Wire executor callbacks to Qt signals
        self.executor.on_plan_started = lambda p: self.plan_started.emit(p)
        self.executor.on_step_started = lambda p, s: self.step_started.emit(p, s)
        self.executor.on_step_completed = lambda p, s: self.step_completed.emit(p, s)
        self.executor.on_step_failed = lambda p, s, err: self.step_failed.emit(p, s, err)
        self.executor.on_plan_paused = lambda p: self.plan_paused.emit(p)
        self.executor.on_plan_resumed = lambda p: self.plan_resumed.emit(p)
        self.executor.on_plan_completed = self._on_plan_completed_internal
        self.executor.on_plan_failed = self._on_plan_failed_internal
        self.executor.on_plan_cancelled = lambda p: self.plan_cancelled.emit(p)

    def _on_plan_completed_internal(self, plan: Plan) -> None:
        self.plan_completed.emit(plan)
        self.plan_notification.emit(
            "Plan Completed",
            f"Successfully executed all {len(plan.steps)} steps for: {plan.goal}",
            "info",
        )

    def _on_plan_failed_internal(self, plan: Plan, error: str) -> None:
        self.plan_failed.emit(plan, error)
        self.plan_notification.emit(
            "Plan Failed",
            f"Plan '{plan.goal}' failed: {error}",
            "warning",
        )

    def create_plan_async(self, goal: str) -> None:
        """Decompose a goal on a background thread and emit plan_generated."""
        def _worker() -> None:
            try:
                plan = self.planner.create_plan(goal)
                self.repository.save_plan(plan)
                self._active_plan = plan
                self.plan_generated.emit(plan)
            except Exception as err:
                logger.exception("Failed to generate plan: %s", err)
                self.plan_notification.emit("Planning Error", str(err), "warning")

        threading.Thread(target=_worker, name="PlanGeneratorWorker", daemon=True).start()

    def start_active_plan(self) -> None:
        """Start execution of current active plan on a background thread."""
        if not self._active_plan:
            return

        def _worker() -> None:
            try:
                self.executor.execute_plan(self._active_plan, interactive=True)
            except Exception as err:
                logger.exception("Error executing plan: %s", err)

        self._execution_thread = threading.Thread(target=_worker, name="PlanExecutorWorker", daemon=True)
        self._execution_thread.start()

    def pause_active_plan(self) -> None:
        """Pause running plan."""
        self.executor.pause()

    def resume_active_plan(self) -> None:
        """Resume paused plan."""
        self.executor.resume()

    def stop_active_plan(self) -> None:
        """Stop / cancel active plan."""
        self.executor.cancel()
