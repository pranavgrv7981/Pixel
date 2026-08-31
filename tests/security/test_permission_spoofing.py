"""Adversarial tests for tool permission spoofing and fake tool aliases."""

import pytest
from app.core.config import Settings
from app.security.manager import PermissionManager
from app.security.permissions import ExecutionContext, PermissionDecision
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.filesystem import DeleteFileTool
from app.tools.registry import ToolRegistry


def test_model_cannot_spoof_tool_risk_level() -> None:
    settings = Settings()
    pm = PermissionManager(settings=settings)
    del_tool = DeleteFileTool(settings=settings)

    # DeleteFileTool is naturally RiskLevel.HIGH
    assert del_tool.risk_level == RiskLevel.HIGH

    # Attempt to spoof execution context with RiskLevel.READ
    spoofed_ctx = ExecutionContext(
        tool_name="delete_file",
        arguments={"path": "data/test.txt"},
        risk_level=RiskLevel.READ,
    )

    # PermissionManager evaluates against the tool's actual registered risk level
    decision = pm.evaluate(del_tool, {"path": "data/test.txt"}, spoofed_ctx)
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.decision == PermissionDecision.CONFIRM


def test_unregistered_tool_aliases_rejected() -> None:
    registry = ToolRegistry()
    fake_names = [
        "delete_file_safe",
        "delete_file_readonly",
        "system.delete_file",
        "eval",
        "exec",
        "powershell",
    ]
    for name in fake_names:
        assert registry.has(name) is False
        with pytest.raises(Exception):
            registry.get(name)
