"""Failure classification, loop breaker, and security denial guard for robust execution recovery."""

import json
from typing import Any, Optional
from app.core.exceptions import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    SecurityError,
    SecurityEvaluationError,
    SecurityPolicyError,
    ToolValidationError,
)
from app.planning.models import FailureType, PlanStep


class FailureClassifier:
    """Classifies runtime step execution errors into structured categories."""

    @staticmethod
    def classify(error: Exception, error_message: str = "") -> FailureType:
        """Categorize an error into a FailureType."""
        msg = (str(error) + " " + error_message).lower()

        if isinstance(error, (PermissionDeniedError, SecurityPolicyError, SecurityEvaluationError, SecurityError)):
            return FailureType.SECURITY_DENIED

        if isinstance(error, ConfirmationRequiredError) or "user rejected" in msg or "confirmation denied" in msg:
            return FailureType.USER_DENIED

        if "timeout" in msg or "timed out" in msg:
            return FailureType.TIMEOUT

        if isinstance(error, ToolValidationError) or "invalid argument" in msg or "validation error" in msg:
            return FailureType.VALIDATION_ERROR

        if "connection refused" in msg or "network unreachable" in msg or "busy" in msg:
            return FailureType.TRANSIENT

        return FailureType.PERMANENT


class LoopDetector:
    """Detects repetitive execution of identical failed steps to prevent endless re-planning cycles."""

    def __init__(self, max_identical_repetitions: int = 2) -> None:
        self.max_identical_repetitions = max_identical_repetitions
        self._history: list[tuple[str, str]] = []

    def record_attempt(self, step: PlanStep) -> bool:
        """Record step attempt and return True if a loop condition is detected."""
        param_key = json.dumps(step.parameters, sort_keys=True, default=str)
        signature = (step.tool_name, param_key)
        self._history.append(signature)

        count = self._history.count(signature)
        return count >= self.max_identical_repetitions


class SecurityDenialGuard:
    """Enforces the strict rule that security denials and user rejections CANNOT be bypassed via re-planning."""

    @staticmethod
    def is_replan_allowed(failure_type: FailureType) -> tuple[bool, Optional[str]]:
        """Return (allowed, reason_if_blocked)."""
        if failure_type == FailureType.SECURITY_DENIED:
            return False, "Security restrictions cannot be bypassed by re-planning."
        if failure_type == FailureType.USER_DENIED:
            return False, "User confirmation denial cannot be bypassed by autonomous re-planning."
        return True, None
