"""Unit tests for FailureRecoveryManager."""

import pytest
from app.agent.intelligence_models import FailureCategory
from app.agent.recovery import FailureRecoveryManager


@pytest.fixture
def recovery_mgr() -> FailureRecoveryManager:
    return FailureRecoveryManager(max_retries=2, max_repetitions=2)


def test_failure_classification_security_denial(recovery_mgr: FailureRecoveryManager) -> None:
    assessment = recovery_mgr.assess_failure(
        "delete_file",
        {"path": "C:/Windows/System32"},
        "Tool execution denied by safety policy: Path outside allowed roots",
    )
    assert assessment.category in {FailureCategory.SECURITY, FailureCategory.PERMISSION_DENIED}
    assert assessment.is_retryable is False
    assert "Cannot retry automatically" in assessment.explanation


def test_failure_classification_not_found(recovery_mgr: FailureRecoveryManager) -> None:
    assessment = recovery_mgr.assess_failure(
        "read_text_file",
        {"path": "data/missing.txt"},
        "File not found: data/missing.txt",
    )
    assert assessment.category == FailureCategory.NOT_FOUND
    assert assessment.is_retryable is False
    assert assessment.safe_alternative == "search_files"


def test_failure_classification_transient_retryable(recovery_mgr: FailureRecoveryManager) -> None:
    assessment1 = recovery_mgr.assess_failure(
        "browser_get_page",
        {"url": "http://localhost:8000"},
        "Network request timed out after 30s",
        current_retries=0,
    )
    assert assessment1.is_retryable is True

    assessment2 = recovery_mgr.assess_failure(
        "browser_get_page",
        {"url": "http://localhost:8000"},
        "Network request timed out after 30s",
        current_retries=2,
    )
    assert assessment2.is_retryable is False
