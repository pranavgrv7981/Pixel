"""Unit tests for PlanExecutor step dispatch, dependency tracking, pause, and cancellation."""

from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.planning.executor import PlanExecutor
from app.planning.models import Plan, PlanStatus, PlanStep, StepStatus
from app.planning.planner import Planner
from app.security.manager import PermissionManager
from app.tools.demo import GetCurrentTimeTool, SafeCalculateTool
from app.tools.registry import ToolRegistry


@pytest.fixture
def executor_setup() -> tuple[PlanExecutor, ToolRegistry, PermissionManager]:
    reg = ToolRegistry()
    reg.register(GetCurrentTimeTool())
    reg.register(SafeCalculateTool())

    perm_mgr = PermissionManager(settings=Settings())
    mock_planner = MagicMock(spec=Planner)
    executor = PlanExecutor(
        registry=reg,
        permission_manager=perm_mgr,
        planner=mock_planner,
        settings=Settings(),
    )
    return executor, reg, perm_mgr


def test_executor_runs_sequential_plan_successfully(executor_setup: tuple[PlanExecutor, ToolRegistry, PermissionManager]) -> None:
    executor, _, _ = executor_setup

    s1 = PlanStep(order=1, description="Get current time", tool_name="get_current_time")
    s2 = PlanStep(order=2, description="Calculate math", tool_name="calculate", parameters={"expression": "10 + 20"}, dependencies=["1"])
    plan = Plan(goal="Execute two steps", steps=[s1, s2])

    result_plan = executor.execute_plan(plan, interactive=True)
    assert result_plan.status == PlanStatus.COMPLETED
    assert s1.status == StepStatus.COMPLETED
    assert s2.status == StepStatus.COMPLETED
    assert "30" in str(s2.result_summary)


def test_executor_blocks_downstream_step_on_dependency_failure(executor_setup: tuple[PlanExecutor, ToolRegistry, PermissionManager]) -> None:
    executor, _, _ = executor_setup

    # S1 will fail due to invalid parameters
    s1 = PlanStep(order=1, description="Bad calculate", tool_name="calculate", parameters={"expression": "invalid expression / 0"})
    s2 = PlanStep(order=2, description="Dependent step", tool_name="get_current_time", dependencies=["1"])
    plan = Plan(goal="Failing plan", steps=[s1, s2])

    # Disable re-planning on mock planner
    executor.planner.replan.return_value = None

    result_plan = executor.execute_plan(plan, interactive=True)
    assert result_plan.status == PlanStatus.FAILED
    assert s1.status == StepStatus.FAILED
    assert s2.status == StepStatus.BLOCKED
