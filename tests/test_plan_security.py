"""Unit tests verifying that PlanExecutor enforces PermissionManager and fail-closed security."""

from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.core.exceptions import PermissionDeniedError
from app.planning.executor import PlanExecutor
from app.planning.models import FailureType, Plan, PlanStatus, PlanStep, StepStatus
from app.planning.planner import Planner
from app.security.manager import PermissionManager
from app.tools.base import RiskLevel
from app.tools.demo import DemoMediumRiskTool, GetCurrentTimeTool
from app.tools.registry import ToolRegistry


def test_plan_execution_denied_when_security_policy_rejects() -> None:
    reg = ToolRegistry()
    reg.register(GetCurrentTimeTool())
    reg.register(DemoMediumRiskTool())

    mock_perm = MagicMock(spec=PermissionManager)
    decision = MagicMock()
    decision.is_allowed = False
    decision.reason = "High risk action strictly forbidden in this context"
    mock_perm.request_permission.return_value = (False, "High risk action strictly forbidden in this context", decision)


    mock_planner = MagicMock(spec=Planner)
    executor = PlanExecutor(
        registry=reg,
        permission_manager=mock_perm,
        planner=mock_planner,
        settings=Settings(),
    )

    step = PlanStep(order=1, description="Medium risk", tool_name="demo_medium_risk_tool", risk_level=RiskLevel.MEDIUM)
    plan = Plan(goal="Risky task", steps=[step])

    result_plan = executor.execute_plan(plan, interactive=False)
    assert result_plan.status == PlanStatus.FAILED
    assert step.status == StepStatus.FAILED
    assert step.failure_type == FailureType.SECURITY_DENIED
    assert "Security policy denied step" in str(step.error_message)
