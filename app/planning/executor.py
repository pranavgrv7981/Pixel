"""Plan execution engine coordinating sequential step dispatch, observations, security checks, and recovery."""

from datetime import datetime, timezone
import time
from typing import Callable, Optional
import uuid

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    SecurityError,
    ToolError,
    ToolExecutionError,
)
from app.core.logging import get_logger
from app.planning.budgets import BudgetTracker
from app.planning.models import FailureType, Plan, PlanStatus, PlanStep, StepStatus
from app.planning.planner import Planner
from app.planning.recovery import FailureClassifier, LoopDetector, SecurityDenialGuard
from app.planning.repository import PlanRepository
from app.security.manager import PermissionManager
from app.security.permissions import ExecutionContext
from app.tools.registry import ToolRegistry

logger = get_logger("planning.executor")


class PlanExecutor:
    """Sequential execution engine managing step lifecycle, permissions, live observations, and controlled recovery."""

    def __init__(
        self,
        registry: ToolRegistry,
        permission_manager: PermissionManager,
        planner: Planner,
        repository: Optional[PlanRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.registry = registry
        self.permission_manager = permission_manager
        self.planner = planner
        self.repository = repository
        self.settings = settings or get_settings()

        self._is_paused: bool = False
        self._is_cancelled: bool = False

        # Event Callbacks
        self.on_plan_started: Optional[Callable[[Plan], None]] = None
        self.on_step_started: Optional[Callable[[Plan, PlanStep], None]] = None
        self.on_step_completed: Optional[Callable[[Plan, PlanStep], None]] = None
        self.on_step_failed: Optional[Callable[[Plan, PlanStep, str], None]] = None
        self.on_plan_paused: Optional[Callable[[Plan], None]] = None
        self.on_plan_resumed: Optional[Callable[[Plan], None]] = None
        self.on_plan_completed: Optional[Callable[[Plan], None]] = None
        self.on_plan_failed: Optional[Callable[[Plan, str], None]] = None
        self.on_plan_cancelled: Optional[Callable[[Plan], None]] = None

    def pause(self) -> None:
        """Pause active plan execution."""
        self._is_paused = True
        logger.info("Plan execution pause requested.")

    def resume(self) -> None:
        """Resume paused plan execution."""
        self._is_paused = False
        logger.info("Plan execution resume requested.")

    def cancel(self) -> None:
        """Cancel active plan execution."""
        self._is_cancelled = True
        logger.info("Plan execution cancel requested.")

    def execute_plan(self, plan: Plan, interactive: bool = True) -> Plan:
        """Execute a validated multi-step plan step-by-step."""
        self._is_paused = False
        self._is_cancelled = False

        plan.status = PlanStatus.RUNNING
        budget_tracker = BudgetTracker(budget=plan.budget, settings=self.settings)
        loop_detector = LoopDetector(max_identical_repetitions=self.settings.max_identical_step_repetitions)

        logger.info("Starting execution of plan '%s' (Goal: '%s', %d steps)...", plan.id, plan.goal, len(plan.steps))
        if self.repository:
            self.repository.save_plan(plan)

        if callable(self.on_plan_started):
            try:
                self.on_plan_started(plan)
            except Exception as err:
                logger.warning("Error in on_plan_started callback: %s", err)

        # Main Step Loop
        current_step_idx = 0
        while current_step_idx < len(plan.steps):
            # Check Cancellation
            if self._is_cancelled:
                plan.status = PlanStatus.CANCELLED
                logger.info("Plan '%s' was cancelled by user.", plan.id)
                self._finalize_plan(plan, "Plan cancelled by user.")
                if callable(self.on_plan_cancelled):
                    self.on_plan_cancelled(plan)
                return plan

            # Check Pause
            if self._is_paused:
                plan.status = PlanStatus.PAUSED
                logger.info("Plan '%s' is paused.", plan.id)
                if callable(self.on_plan_paused):
                    self.on_plan_paused(plan)
                while self._is_paused and not self._is_cancelled:
                    time.sleep(0.2)
                if self._is_cancelled:
                    continue
                plan.status = PlanStatus.RUNNING
                logger.info("Plan '%s' resumed.", plan.id)
                if callable(self.on_plan_resumed):
                    self.on_plan_resumed(plan)

            # Check Budget
            is_exhausted, exhaust_reason = budget_tracker.check_budget()
            if is_exhausted:
                plan.status = PlanStatus.FAILED
                reason = f"Execution halted: {exhaust_reason}"
                logger.warning("Plan '%s' budget exhausted: %s", plan.id, reason)
                self._finalize_plan(plan, reason)
                if callable(self.on_plan_failed):
                    self.on_plan_failed(plan, reason)
                return plan

            step = plan.steps[current_step_idx]

            # Check Dependencies
            prereqs_ok, block_reason = self._check_step_dependencies(plan, step)
            if not prereqs_ok:
                step.status = StepStatus.BLOCKED
                step.error_message = block_reason
                logger.warning("Step %d ('%s') blocked: %s", step.order, step.description, block_reason)
                current_step_idx += 1
                continue

            # Execute Step
            success = self._execute_step(plan, step, interactive, budget_tracker, loop_detector)

            if not success:
                # Handle Failure & Controlled Re-planning
                budget_tracker.record_failure()
                replan_allowed, replan_reason = SecurityDenialGuard.is_replan_allowed(
                    step.failure_type or FailureType.UNKNOWN
                )

                if replan_allowed and plan.budget.replans_count < plan.budget.max_replans:
                    budget_tracker.record_replan()
                    repaired = self.planner.replan(plan, step, step.error_message or "Unknown error")
                    if repaired:
                        # Adopt repaired plan steps
                        plan.steps = repaired.steps
                        plan.version = repaired.version
                        current_step_idx = 0  # Re-evaluate from first pending step
                        continue

                # If re-planning not possible/allowed, mark remaining dependent steps blocked and fail plan
                self._block_remaining_dependent_steps(plan, step)
                plan.status = PlanStatus.FAILED
                fail_msg = f"Plan failed at step {step.order} ('{step.description}'): {step.error_message}"
                self._finalize_plan(plan, fail_msg)
                if callable(self.on_plan_failed):
                    self.on_plan_failed(plan, fail_msg)
                return plan

            current_step_idx += 1

        # All steps processed
        all_completed = all(s.status == StepStatus.COMPLETED for s in plan.steps)
        if all_completed:
            plan.status = PlanStatus.COMPLETED
            summary = f"Plan completed successfully ({len(plan.steps)}/{len(plan.steps)} steps)."
            logger.info("Plan '%s' completed successfully.", plan.id)
            self._finalize_plan(plan, summary)
            if callable(self.on_plan_completed):
                self.on_plan_completed(plan)
        else:
            plan.status = PlanStatus.FAILED
            summary = "Plan completed with unexecuted or blocked steps."
            self._finalize_plan(plan, summary)
            if callable(self.on_plan_failed):
                self.on_plan_failed(plan, summary)

        return plan

    def _execute_step(
        self,
        plan: Plan,
        step: PlanStep,
        interactive: bool,
        budget_tracker: BudgetTracker,
        loop_detector: LoopDetector,
    ) -> bool:
        """Execute a single plan step, enforcing permissions, retries, and recording observations."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc)
        start_clock = time.perf_counter()

        logger.info("Executing step %d: %s [%s]...", step.order, step.description, step.tool_name)
        if callable(self.on_step_started):
            try:
                self.on_step_started(plan, step)
            except Exception as err:
                logger.warning("Error in on_step_started callback: %s", err)

        # 1. Loop Detection
        if loop_detector.record_attempt(step):
            step.status = StepStatus.FAILED
            step.failure_type = FailureType.PERMANENT
            step.error_message = f"Loop breaker triggered: step '{step.tool_name}' failed repeatedly."
            logger.error("Loop detected on step %d: %s", step.order, step.error_message)
            return False

        # 1. Tool Lookup
        if not self.registry.has(step.tool_name):
            step.status = StepStatus.FAILED
            step.failure_type = FailureType.VALIDATION_ERROR
            step.error_message = f"Registered tool '{step.tool_name}' not found."
            return False

        tool = self.registry.get(step.tool_name)


        # 2. Permission Evaluation
        exec_ctx = ExecutionContext(
            tool_name=tool.name,
            risk_level=tool.risk_level,
            arguments=step.parameters,
            user_id="local_user",
            interactive=interactive,
            source="planner",
            conversation_id=plan.id,
            reason=step.description,
        )

        try:
            allowed, reason, _ = self.permission_manager.request_permission(
                tool=tool,
                arguments=step.parameters,
                context=exec_ctx,
            )
            if not allowed:
                step.status = StepStatus.FAILED
                step.failure_type = FailureType.SECURITY_DENIED
                step.error_message = f"Security policy denied step: {reason}"
                logger.warning("Permission denied for step %d: %s", step.order, reason)
                return False
        except ConfirmationRequiredError:
            step.status = StepStatus.BLOCKED
            step.failure_type = FailureType.USER_DENIED
            step.error_message = "Confirmation required but rejected or non-interactive."
            logger.warning("Confirmation not granted for step %d", step.order)
            return False
        except Exception as sec_err:
            step.status = StepStatus.FAILED
            step.failure_type = FailureType.SECURITY_DENIED
            step.error_message = f"Security evaluation error: {sec_err}"
            logger.warning("Security evaluation exception for step %d: %s", step.order, sec_err)
            return False

        budget_tracker.record_step_execution()
        budget_tracker.record_tool_call()


        try:
            result = tool.execute(step.parameters)
            duration = time.perf_counter() - start_clock
            step.duration_seconds = round(duration, 3)
            step.completed_at = datetime.now(timezone.utc)

            if result.success:
                step.status = StepStatus.COMPLETED
                step.result_summary = str(result.message or result.data or result.to_llm_content() or "Success")[:500]
                logger.info("Step %d completed in %.3fs.", step.order, duration)
                if callable(self.on_step_completed):
                    self.on_step_completed(plan, step)
                return True
            else:
                step.status = StepStatus.FAILED
                step.failure_type = FailureType.PERMANENT
                step.error_message = str(result.error or result.message or "Tool returned failure.")
                logger.warning("Step %d tool failed: %s", step.order, step.error_message)
                if callable(self.on_step_failed):
                    self.on_step_failed(plan, step, step.error_message)
                return False


        except Exception as err:
            duration = time.perf_counter() - start_clock
            step.duration_seconds = round(duration, 3)
            step.completed_at = datetime.now(timezone.utc)
            step.status = StepStatus.FAILED
            step.failure_type = FailureClassifier.classify(err)
            step.error_message = str(err)
            logger.exception("Exception executing step %d: %s", step.order, err)

            # Retry transient errors if within budget
            if step.failure_type == FailureType.TRANSIENT and step.retries_used < self.settings.max_step_retries:
                step.retries_used += 1
                logger.info("Retrying transient step failure (attempt %d/%d)...", step.retries_used, self.settings.max_step_retries)
                time.sleep(0.5)
                return self._execute_step(plan, step, interactive, budget_tracker, loop_detector)

            if callable(self.on_step_failed):
                self.on_step_failed(plan, step, step.error_message)
            return False

    def _check_step_dependencies(self, plan: Plan, step: PlanStep) -> tuple[bool, Optional[str]]:
        """Verify that all prerequisite dependencies of a step completed successfully."""
        if not step.dependencies:
            return True, None

        for dep in step.dependencies:
            prereq = plan.get_step_by_id(dep) or plan.get_step_by_order(int(dep) if dep.isdigit() else -1)
            if not prereq:
                return False, f"Prerequisite dependency '{dep}' does not exist in plan."
            if prereq.status != StepStatus.COMPLETED:
                return False, f"Prerequisite step {prereq.order} ('{prereq.description}') has status '{prereq.status.value}'."

        return True, None

    def _block_remaining_dependent_steps(self, plan: Plan, failed_step: PlanStep) -> None:
        """Mark unexecuted downstream dependent steps as BLOCKED."""
        for s in plan.steps:
            if s.status == StepStatus.PENDING:
                if str(failed_step.order) in s.dependencies or failed_step.id in s.dependencies:
                    s.status = StepStatus.BLOCKED
                    s.error_message = f"Blocked by failure of step {failed_step.order}."

    def _finalize_plan(self, plan: Plan, summary: str) -> None:
        """Persist final state and record completion timestamp."""
        plan.completed_at = datetime.now(timezone.utc)
        plan.final_summary = summary
        if self.repository:
            try:
                self.repository.save_plan(plan)
            except Exception as err:
                logger.warning("Error persisting final plan state: %s", err)
