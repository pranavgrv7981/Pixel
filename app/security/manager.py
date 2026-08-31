"""Centralized permission manager orchestrating policy checks, confirmation prompts, and auditing."""

from typing import Any, Optional

from app.core.config import Settings
from app.core.logging import get_logger
from app.security.audit import AuditLogger
from app.security.confirmations import ConfirmationManager
from app.security.permissions import (
    ExecutionContext,
    PermissionDecision,
    SecurityDecision,
)
from app.security.policies import SecurityPolicy
from app.tools.base import Tool

logger = get_logger("security.manager")


class PermissionManager:
    """Central authority governing tool execution permissions, confirmation, and security audit."""

    def __init__(
        self,
        policy: Optional[SecurityPolicy] = None,
        confirmation_manager: Optional[ConfirmationManager] = None,
        audit_logger: Optional[AuditLogger] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.policy: SecurityPolicy = policy or SecurityPolicy.from_settings(settings)
        self.confirmation_manager: ConfirmationManager = confirmation_manager or ConfirmationManager()
        self.audit_logger: AuditLogger = audit_logger or AuditLogger()

    def evaluate(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> SecurityDecision:
        """Evaluate a tool execution attempt against configured security policies."""
        ctx = context or ExecutionContext(
            tool_name=tool.name,
            arguments=arguments,
            risk_level=tool.risk_level,
        )

        decision, reason = self.policy.evaluate(
            tool_name=tool.name,
            risk_level=tool.risk_level,
            arguments=arguments,
        )

        return SecurityDecision(
            decision=decision,
            reason=reason,
            tool_name=tool.name,
            risk_level=tool.risk_level,
            request_id=ctx.request_id,
            requires_user_confirmation=(decision == PermissionDecision.CONFIRM),
        )

    def request_permission(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> tuple[bool, str, SecurityDecision]:
        """Request permission to execute a tool, resolving confirmations and logging audits.

        Returns:
            Tuple of (is_allowed: bool, reason: str, decision: SecurityDecision).
            Guaranteed to fail closed on any internal exception.
        """
        ctx = context or ExecutionContext(
            tool_name=tool.name,
            arguments=arguments,
            risk_level=tool.risk_level,
        )

        try:
            self.audit_logger.log_permission_requested(ctx)
            sec_decision = self.evaluate(tool, arguments, ctx)

            if sec_decision.decision == PermissionDecision.ALLOW:
                self.audit_logger.log_permission_allowed(ctx, sec_decision)
                return True, sec_decision.reason, sec_decision

            if sec_decision.decision == PermissionDecision.DENY:
                self.audit_logger.log_permission_denied(ctx, sec_decision)
                return False, sec_decision.reason, sec_decision

            if sec_decision.decision == PermissionDecision.CONFIRM:
                self.audit_logger.log_confirmation_requested(ctx, sec_decision)
                approved = self.confirmation_manager.request_confirmation(ctx, sec_decision)
                if approved:
                    self.audit_logger.log_confirmation_approved(ctx, sec_decision)
                    return True, "Action approved by user confirmation", sec_decision
                else:
                    self.audit_logger.log_confirmation_rejected(ctx, sec_decision)
                    return False, "Action denied: User declined or confirmation unavailable", sec_decision

            # Default fail-closed fallback
            self.audit_logger.log_permission_denied(ctx, sec_decision)
            return False, "Permission decision unresolved; failing closed", sec_decision

        except Exception as err:
            logger.error("Internal security evaluation exception for '%s': %s; failing closed", tool.name, err)
            self.audit_logger.log_security_error(ctx, str(err))
            fallback_decision = SecurityDecision(
                decision=PermissionDecision.DENY,
                reason=f"Security error: {err}",
                tool_name=tool.name,
                risk_level=tool.risk_level,
                request_id=ctx.request_id,
                requires_user_confirmation=False,
            )
            return False, f"Internal security check failed: {err}", fallback_decision
