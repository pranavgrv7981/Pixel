"""Budget tracker and resource limiter for plan execution."""

import time
from typing import Optional
from app.core.config import Settings, get_settings
from app.planning.models import PlanBudget


class BudgetTracker:
    """Manages real-time resource tracking and enforce execution budgets on active plans."""

    def __init__(self, budget: Optional[PlanBudget] = None, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        if budget:
            self.budget = budget
        else:
            self.budget = PlanBudget(
                max_steps=self.settings.max_plan_steps,
                max_tool_calls=self.settings.max_plan_tool_calls,
                max_runtime_seconds=float(self.settings.max_plan_runtime_seconds),
                max_failures=self.settings.max_plan_failures,
                max_replans=self.settings.max_replans,
            )
        self._start_time: float = time.perf_counter()

    def record_step_execution(self) -> None:
        """Increment executed steps counter."""
        self.budget.steps_executed += 1
        self._update_runtime()

    def record_tool_call(self) -> None:
        """Increment tool calls counter."""
        self.budget.tool_calls_used += 1
        self._update_runtime()

    def record_failure(self) -> None:
        """Increment failed steps counter."""
        self.budget.failures_count += 1
        self._update_runtime()

    def record_replan(self) -> None:
        """Increment re-plans counter."""
        self.budget.replans_count += 1
        self._update_runtime()

    def _update_runtime(self) -> None:
        """Update elapsed execution time."""
        self.budget.runtime_seconds_used = time.perf_counter() - self._start_time

    def check_budget(self) -> tuple[bool, Optional[str]]:
        """Return (is_exhausted, reason_if_exhausted)."""
        self._update_runtime()
        return self.budget.is_exhausted()
