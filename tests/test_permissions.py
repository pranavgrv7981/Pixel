"""Tests for app/security/permissions.py and app/security/policies.py."""

import pytest

from app.core.exceptions import SecurityPolicyError
from app.security.permissions import (
    ExecutionContext,
    PermissionDecision,
    SecurityDecision,
)
from app.security.policies import SecurityPolicy
from app.tools.base import RiskLevel


def test_permission_decision_enum() -> None:
    """Verify PermissionDecision values."""
    assert PermissionDecision.ALLOW.value == "ALLOW"
    assert PermissionDecision.DENY.value == "DENY"
    assert PermissionDecision.CONFIRM.value == "CONFIRM"


def test_execution_context_defaults() -> None:
    """Verify ExecutionContext fields and defaults."""
    ctx = ExecutionContext(
        tool_name="test_tool",
        risk_level=RiskLevel.LOW,
    )
    assert ctx.tool_name == "test_tool"
    assert ctx.risk_level == RiskLevel.LOW
    assert len(ctx.request_id) > 0
    assert ctx.arguments == {}
    assert ctx.source == "agent"
    assert ctx.interactive is False


def test_security_decision_creation() -> None:
    """Verify SecurityDecision fields."""
    decision = SecurityDecision(
        decision=PermissionDecision.CONFIRM,
        reason="Action requires user approval",
        tool_name="delete_something",
        risk_level=RiskLevel.MEDIUM,
        request_id="req-123",
        requires_user_confirmation=True,
    )
    assert decision.decision == PermissionDecision.CONFIRM
    assert decision.requires_user_confirmation is True
    assert decision.request_id == "req-123"


def test_policy_defaults() -> None:
    """Verify default conservative policy matrix."""
    policy = SecurityPolicy()

    # READ -> ALLOW
    dec, _ = policy.evaluate("get_time", RiskLevel.READ)
    assert dec == PermissionDecision.ALLOW

    # LOW -> ALLOW
    dec, _ = policy.evaluate("simple_calc", RiskLevel.LOW)
    assert dec == PermissionDecision.ALLOW

    # MEDIUM -> CONFIRM
    dec, _ = policy.evaluate("change_setting", RiskLevel.MEDIUM)
    assert dec == PermissionDecision.CONFIRM

    # HIGH -> CONFIRM
    dec, _ = policy.evaluate("write_file", RiskLevel.HIGH)
    assert dec == PermissionDecision.CONFIRM

    # CRITICAL -> DENY
    dec, _ = policy.evaluate("format_disk", RiskLevel.CRITICAL)
    assert dec == PermissionDecision.DENY


def test_policy_allow_critical_disabled() -> None:
    """Verify CRITICAL risk tools are blocked by default."""
    policy = SecurityPolicy(allow_critical=False)
    dec, reason = policy.evaluate("critical_tool", RiskLevel.CRITICAL)
    assert dec == PermissionDecision.DENY
    assert "CRITICAL" in reason



def test_policy_allow_critical_enabled() -> None:
    """Verify CRITICAL risk tools require confirmation if explicitly permitted."""
    policy = SecurityPolicy(allow_critical=True)
    dec, reason = policy.evaluate("critical_tool", RiskLevel.CRITICAL)
    assert dec == PermissionDecision.CONFIRM
    assert "CRITICAL risk tool requires explicit confirmation" in reason


def test_policy_tool_specific_override() -> None:
    """Verify tool-specific overrides take precedence."""
    policy = SecurityPolicy(
        tool_overrides={
            "special_tool": PermissionDecision.ALLOW,
            "blocked_tool": PermissionDecision.DENY,
        }
    )

    # Overridden MEDIUM risk tool auto-allowed
    dec1, _ = policy.evaluate("special_tool", RiskLevel.MEDIUM)
    assert dec1 == PermissionDecision.ALLOW

    # Overridden READ risk tool denied
    dec2, _ = policy.evaluate("blocked_tool", RiskLevel.READ)
    assert dec2 == PermissionDecision.DENY


def test_policy_override_cannot_bypass_critical() -> None:
    """Verify an override to ALLOW on a CRITICAL tool is rejected when allow_critical is False."""
    policy = SecurityPolicy(
        allow_critical=False,
        tool_overrides={"dangerous_critical": PermissionDecision.ALLOW},
    )
    dec, reason = policy.evaluate("dangerous_critical", RiskLevel.CRITICAL)
    assert dec == PermissionDecision.DENY
    assert "CRITICAL" in reason


def test_policy_invalid_override_raises() -> None:
    """Verify invalid overrides raise SecurityPolicyError."""
    with pytest.raises(SecurityPolicyError):
        SecurityPolicy(tool_overrides={"": PermissionDecision.ALLOW})

    with pytest.raises(SecurityPolicyError):
        SecurityPolicy(tool_overrides={"tool": "NOT_A_DECISION"})  # type: ignore
