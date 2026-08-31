"""Unit tests for BudgetTracker runtime and limit tracking."""

import pytest
from app.planning.budgets import BudgetTracker
from app.planning.models import PlanBudget


def test_budget_tracker_records_executions_and_fails_on_limit() -> None:
    budget = PlanBudget(max_steps=2, max_tool_calls=2)
    tracker = BudgetTracker(budget=budget)

    exhausted, _ = tracker.check_budget()
    assert exhausted is False

    tracker.record_step_execution()
    tracker.record_tool_call()
    assert tracker.budget.steps_executed == 1
    assert tracker.budget.tool_calls_used == 1

    tracker.record_step_execution()
    tracker.record_tool_call()
    exhausted, reason = tracker.check_budget()
    assert exhausted is True
    assert "Step limit reached" in str(reason)
