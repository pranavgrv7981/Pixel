"""Adversarial tests for planner privilege escalation and replanning attack defense."""

import pytest
from app.planning.models import FailureType, Plan, PlanStep, StepStatus
from app.planning.recovery import SecurityDenialGuard
from app.planning.validator import PlanValidator
from app.tools.registry import ToolRegistry
from app.tools.demo import SafeCalculateTool


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(SafeCalculateTool())
    return reg


@pytest.fixture
def validator(registry: ToolRegistry) -> PlanValidator:
    return PlanValidator(registry=registry)


def test_planner_cannot_invent_unregistered_tools(validator: PlanValidator) -> None:
    plan = Plan(
        goal="Bypass security",
        steps=[
            PlanStep(
                order=1,
                description="Run shell command",
                tool_name="unregistered_shell_tool",
                parameters={"command": "dir"},
            )
        ]
    )
    is_valid, errors = validator.validate_plan(plan)
    assert is_valid is False
    assert any("unknown tool" in err.lower() for err in errors)


def test_security_denial_guard_blocks_replan_after_safety_rejection() -> None:
    guard = SecurityDenialGuard()

    # Step was denied by safety policy -> is_replan_allowed must return False
    allowed, reason = guard.is_replan_allowed(FailureType.SECURITY_DENIED)
    assert allowed is False
    assert "Security restrictions cannot be bypassed" in reason
