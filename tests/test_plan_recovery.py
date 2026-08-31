"""Unit tests for FailureClassifier, LoopDetector, and SecurityDenialGuard."""

import pytest
from app.core.exceptions import PermissionDeniedError, ToolValidationError
from app.planning.models import FailureType, PlanStep
from app.planning.recovery import FailureClassifier, LoopDetector, SecurityDenialGuard


def test_failure_classifier_detects_security_and_validation() -> None:
    sec_err = PermissionDeniedError("Access denied by execution policy")
    assert FailureClassifier.classify(sec_err) == FailureType.SECURITY_DENIED

    val_err = ToolValidationError("Missing parameter")
    assert FailureClassifier.classify(val_err) == FailureType.VALIDATION_ERROR

    time_err = TimeoutError("Command timed out after 30s")
    assert FailureClassifier.classify(time_err) == FailureType.TIMEOUT


def test_security_denial_guard_blocks_replan() -> None:
    allowed, reason = SecurityDenialGuard.is_replan_allowed(FailureType.SECURITY_DENIED)
    assert allowed is False
    assert "Security restrictions cannot be bypassed" in str(reason)

    allowed, _ = SecurityDenialGuard.is_replan_allowed(FailureType.TRANSIENT)
    assert allowed is True


def test_loop_detector_breaks_identical_repetition() -> None:
    detector = LoopDetector(max_identical_repetitions=2)
    step = PlanStep(order=1, description="Repeat tool", tool_name="calculate", parameters={"expression": "1+1"})

    assert detector.record_attempt(step) is False
    assert detector.record_attempt(step) is True
