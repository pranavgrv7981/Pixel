from app.core.config import Settings
from app.core.exceptions import PermissionDeniedError, TaskValidationError
from app.security.manager import PermissionManager
from app.security.permissions import ExecutionContext, PermissionDecision
from app.tasks.security import (
    FORBIDDEN_AUTONOMOUS_TOOLS,
    check_recursive_task_creation,
    validate_task_action,
)
from app.tasks.models import TaskActionType
from app.tools.base import RiskLevel


def test_forbidden_autonomous_tools_set() -> None:
    # Ensure dangerous tools are forbidden from automated scheduled execution without confirmation
    assert "delete_file" in FORBIDDEN_AUTONOMOUS_TOOLS
    assert "run_python_file" in FORBIDDEN_AUTONOMOUS_TOOLS
    assert "run_c_program" in FORBIDDEN_AUTONOMOUS_TOOLS
    assert "compile_c_program" in FORBIDDEN_AUTONOMOUS_TOOLS
    assert "browser_click" in FORBIDDEN_AUTONOMOUS_TOOLS
    assert "browser_type" in FORBIDDEN_AUTONOMOUS_TOOLS


def test_recursive_task_creation_check() -> None:
    # When running inside non-interactive background scheduler or event context
    assert check_recursive_task_creation("create_task", is_background_context=True) is False
    assert check_recursive_task_creation("run_task_now", is_background_context=True) is False

    # Normal read or calculation tools are allowed
    assert check_recursive_task_creation("safe_calculate", is_background_context=True) is True
    assert check_recursive_task_creation("recall_memory", is_background_context=True) is True


def test_non_interactive_confirmation_fails_closed() -> None:
    from unittest.mock import MagicMock
    from app.tools.base import Tool

    # Permission manager with NO interactive confirmation provider must DENY/reject medium/high risk
    perm_mgr = PermissionManager(settings=Settings())
    mock_tool = MagicMock(spec=Tool)
    mock_tool.name = "delete_file"
    mock_tool.risk_level = RiskLevel.HIGH

    allowed, reason, decision = perm_mgr.request_permission(mock_tool, {"path": "test.txt"})
    assert allowed is False
    assert "rejected" in reason.lower() or "denied" in reason.lower()


