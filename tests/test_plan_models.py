"""Unit tests for planning data models, step statuses, and budget tracking."""

import pytest
from app.planning.models import (
    FailureType,
    Plan,
    PlanBudget,
    PlanStatus,
    PlanStep,
    StepStatus,
)
from app.tools.base import RiskLevel


def test_plan_step_creation_and_status_defaults() -> None:
    step = PlanStep(
        order=1,
        description="Inspect files",
        tool_name="list_directory",
        parameters={"directory_path": "data"},
    )
    assert step.status == StepStatus.PENDING
    assert step.risk_level == RiskLevel.READ
    assert step.is_finished() is False
    assert step.retries_used == 0


def test_plan_safety_assessment_evaluates_riskiest_step() -> None:
    safe_step = PlanStep(order=1, description="Read", tool_name="list_directory", risk_level=RiskLevel.READ)
    risky_step = PlanStep(order=2, description="Write", tool_name="delete_file", risk_level=RiskLevel.HIGH)

    # Safe plan
    safe_plan = Plan(goal="Read data", steps=[safe_step])
    safe_plan.update_safety_assessment()
    assert safe_plan.is_safe_plan is True
    assert safe_plan.requires_user_approval is False

    # Risky plan
    risky_plan = Plan(goal="Cleanup data", steps=[safe_step, risky_step])
    risky_plan.update_safety_assessment()
    assert risky_plan.is_safe_plan is False
    assert risky_plan.requires_user_approval is True


def test_plan_budget_exhaustion_checks() -> None:
    budget = PlanBudget(max_steps=2, max_failures=1)
    exhausted, _ = budget.is_exhausted()
    assert exhausted is False

    budget.steps_executed = 2
    exhausted, reason = budget.is_exhausted()
    assert exhausted is True
    assert "Step limit reached" in str(reason)
