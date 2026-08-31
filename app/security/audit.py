"""Structured security audit logging."""

import json
from typing import Any, Mapping

from app.core.logging import get_logger, redact_sensitive_text
from app.security.permissions import ExecutionContext, SecurityDecision

logger = get_logger("security.audit")

_SENSITIVE_PATTERNS = {"password", "secret", "token", "key", "auth", "credential", "private", "api_key"}


def scrub_sensitive_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize argument dictionaries by redacting sensitive keys and values."""
    scrubbed: dict[str, Any] = {}
    for k, v in data.items():
        k_lower = str(k).lower()
        if any(pat in k_lower for pat in _SENSITIVE_PATTERNS):
            scrubbed[k] = "******"
        elif isinstance(v, Mapping):
            scrubbed[k] = scrub_sensitive_dict(v)
        elif isinstance(v, str):
            scrubbed[k] = redact_sensitive_text(v)
        else:
            scrubbed[k] = v
    return scrubbed


class AuditLogger:
    """Records security-relevant events into centralized application logs."""

    def __init__(self) -> None:
        self.logger = logger

    def log_permission_requested(self, context: ExecutionContext) -> None:
        args_safe = scrub_sensitive_dict(context.arguments)
        self.logger.info(
            "AUDIT [permission_requested] req_id=%s tool=%s risk=%s args=%s",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
            json.dumps(args_safe, default=str),
        )

    def log_permission_allowed(self, context: ExecutionContext, decision: SecurityDecision) -> None:
        self.logger.info(
            "AUDIT [permission_allowed] req_id=%s tool=%s risk=%s reason='%s'",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
            decision.reason,
        )

    def log_permission_denied(self, context: ExecutionContext, decision: SecurityDecision) -> None:
        self.logger.warning(
            "AUDIT [permission_denied] req_id=%s tool=%s risk=%s reason='%s'",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
            decision.reason,
        )

    def log_confirmation_requested(self, context: ExecutionContext, decision: SecurityDecision) -> None:
        self.logger.info(
            "AUDIT [confirmation_requested] req_id=%s tool=%s risk=%s reason='%s'",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
            decision.reason,
        )

    def log_confirmation_approved(self, context: ExecutionContext, decision: SecurityDecision) -> None:
        self.logger.info(
            "AUDIT [confirmation_approved] req_id=%s tool=%s risk=%s",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
        )

    def log_confirmation_rejected(self, context: ExecutionContext, decision: SecurityDecision) -> None:
        self.logger.warning(
            "AUDIT [confirmation_rejected] req_id=%s tool=%s risk=%s",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
        )

    def log_tool_execution_blocked(self, context: ExecutionContext, reason: str) -> None:
        self.logger.warning(
            "AUDIT [tool_execution_blocked] req_id=%s tool=%s risk=%s reason='%s'",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
            reason,
        )

    def log_security_error(self, context: ExecutionContext, error: str) -> None:
        self.logger.error(
            "AUDIT [security_error] req_id=%s tool=%s risk=%s error='%s'",
            context.request_id,
            context.tool_name,
            context.risk_level.value,
            error,
        )
