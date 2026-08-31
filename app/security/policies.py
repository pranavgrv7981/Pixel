"""Security policy engine defining risk-based evaluation and tool-level overrides."""

from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import SecurityPolicyError
from app.security.permissions import PermissionDecision
from app.tools.base import RiskLevel


class SecurityPolicy:
    """Evaluates security rules and overrides to determine execution permission."""

    def __init__(
        self,
        auto_approve_read: bool = True,
        auto_approve_low: bool = True,
        require_confirmation_medium: bool = True,
        require_confirmation_high: bool = True,
        allow_critical: bool = False,
        tool_overrides: Optional[dict[str, PermissionDecision]] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        if settings is not None:
            self.auto_approve_read = settings.auto_approve_read_tools
            self.auto_approve_low = settings.auto_approve_low_risk_tools
            self.require_confirmation_medium = settings.require_confirmation_medium
            self.require_confirmation_high = settings.require_confirmation_high
            self.allow_critical = settings.allow_critical_tools
        else:
            self.auto_approve_read = auto_approve_read
            self.auto_approve_low = auto_approve_low
            self.require_confirmation_medium = require_confirmation_medium
            self.require_confirmation_high = require_confirmation_high
            self.allow_critical = allow_critical

        self.tool_overrides: dict[str, PermissionDecision] = {}
        if tool_overrides:
            for name, decision in tool_overrides.items():
                if not isinstance(name, str) or not name.strip():
                    raise SecurityPolicyError("Tool override name must be a non-empty string")
                if not isinstance(decision, PermissionDecision):
                    raise SecurityPolicyError(f"Invalid override decision for '{name}': {decision}")
                self.tool_overrides[name.strip()] = decision

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "SecurityPolicy":
        """Construct SecurityPolicy directly from application settings."""
        cfg = settings or get_settings()
        return cls(settings=cfg)

    def evaluate(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        arguments: Optional[dict[str, Any]] = None,
    ) -> tuple[PermissionDecision, str]:
        """Evaluate a tool execution attempt against risk policies and overrides.

        Returns:
            Tuple of (PermissionDecision, explanation_string).
        """
        # 1. Absolute critical block if allow_critical is False
        if risk_level == RiskLevel.CRITICAL and not self.allow_critical:
            return (
                PermissionDecision.DENY,
                f"Tool '{tool_name}' has CRITICAL risk and critical tool execution is disabled by policy",
            )

        # 2. Check tool-specific overrides
        if tool_name in self.tool_overrides:
            override = self.tool_overrides[tool_name]
            if risk_level == RiskLevel.CRITICAL and override == PermissionDecision.ALLOW and not self.allow_critical:
                return (
                    PermissionDecision.DENY,
                    f"Override for '{tool_name}' cannot bypass CRITICAL safety restriction",
                )
            return (override, f"Tool '{tool_name}' matched explicit policy override: {override.value}")

        # 3. Standard Risk Matrix Evaluation
        if risk_level == RiskLevel.READ:
            if self.auto_approve_read:
                return (PermissionDecision.ALLOW, "READ risk tool is auto-approved by policy")
            return (PermissionDecision.CONFIRM, "READ risk tool requires user confirmation per policy")

        if risk_level == RiskLevel.LOW:
            if self.auto_approve_low:
                return (PermissionDecision.ALLOW, "LOW risk tool is auto-approved by policy")
            return (PermissionDecision.CONFIRM, "LOW risk tool requires user confirmation per policy")

        if risk_level == RiskLevel.MEDIUM:
            if self.require_confirmation_medium:
                return (PermissionDecision.CONFIRM, "MEDIUM risk tool requires explicit user confirmation")
            return (PermissionDecision.ALLOW, "MEDIUM risk tool is auto-approved by relaxed policy")

        if risk_level == RiskLevel.HIGH:
            if self.require_confirmation_high:
                return (PermissionDecision.CONFIRM, "HIGH risk tool requires explicit user confirmation")
            return (PermissionDecision.ALLOW, "HIGH risk tool is auto-approved by relaxed policy")

        if risk_level == RiskLevel.CRITICAL:
            if self.allow_critical:
                return (PermissionDecision.CONFIRM, "CRITICAL risk tool requires explicit confirmation")
            return (PermissionDecision.DENY, "CRITICAL risk tools are prohibited")

        # 4. Fail-closed on any unrecognized risk level
        return (PermissionDecision.DENY, f"Unrecognized risk level '{risk_level}'; failing closed")
