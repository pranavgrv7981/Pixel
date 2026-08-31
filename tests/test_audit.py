"""Tests for app/security/audit.py."""

from unittest.mock import MagicMock
import pytest

from app.security.audit import AuditLogger, scrub_sensitive_dict
from app.security.permissions import (
    ExecutionContext,
    PermissionDecision,
    SecurityDecision,
)
from app.tools.base import RiskLevel


def test_scrub_sensitive_dict() -> None:
    """Verify sensitive keys are redacted from audit logging dictionaries."""
    data = {
        "username": "alice",
        "password": "supersecretpassword",
        "api_key": "sk-1234567890",
        "auth_token": "token_abc",
        "nested": {
            "secret_key": "nested_secret",
            "safe_field": "visible",
        },
    }

    scrubbed = scrub_sensitive_dict(data)
    assert scrubbed["username"] == "alice"
    assert scrubbed["password"] == "******"
    assert scrubbed["api_key"] == "******"
    assert scrubbed["auth_token"] == "******"
    assert scrubbed["nested"]["secret_key"] == "******"
    assert scrubbed["nested"]["safe_field"] == "visible"


def test_audit_logger_events() -> None:
    """Verify AuditLogger logs structured security events."""
    audit = AuditLogger()
    audit.logger = MagicMock()

    ctx = ExecutionContext(
        tool_name="test_tool",
        arguments={"api_key": "12345", "param": "val"},
        risk_level=RiskLevel.MEDIUM,
    )
    decision = SecurityDecision(
        decision=PermissionDecision.ALLOW,
        reason="Test allowed",
        tool_name="test_tool",
        risk_level=RiskLevel.MEDIUM,
        request_id=ctx.request_id,
        requires_user_confirmation=False,
    )

    audit.log_permission_requested(ctx)
    assert audit.logger.info.called

    audit.log_permission_allowed(ctx, decision)
    assert audit.logger.info.called

    audit.log_permission_denied(ctx, decision)
    assert audit.logger.warning.called

    audit.log_confirmation_requested(ctx, decision)
    assert audit.logger.info.called

    audit.log_confirmation_approved(ctx, decision)
    assert audit.logger.info.called

    audit.log_confirmation_rejected(ctx, decision)
    assert audit.logger.warning.called

    audit.log_tool_execution_blocked(ctx, "Policy denial")
    assert audit.logger.warning.called

    audit.log_security_error(ctx, "Internal security failure")
    assert audit.logger.error.called
