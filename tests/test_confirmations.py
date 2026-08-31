"""Tests for app/security/confirmations.py."""

from unittest.mock import MagicMock
import pytest

from app.security.confirmations import (
    CliConfirmationProvider,
    ConfirmationManager,
    ConfirmationProvider,
    NonInteractiveConfirmationProvider,
)
from app.security.permissions import (
    ExecutionContext,
    PermissionDecision,
    SecurityDecision,
)
from app.tools.base import RiskLevel


@pytest.fixture
def sample_context() -> ExecutionContext:
    return ExecutionContext(
        tool_name="test_tool",
        arguments={"param": "value"},
        risk_level=RiskLevel.MEDIUM,
    )


@pytest.fixture
def sample_decision() -> SecurityDecision:
    return SecurityDecision(
        decision=PermissionDecision.CONFIRM,
        reason="Test confirmation",
        tool_name="test_tool",
        risk_level=RiskLevel.MEDIUM,
        request_id="req-test-1",
        requires_user_confirmation=True,
    )


@pytest.mark.parametrize("affirmative", ["y", "Y", "yes", "YES", "  y  "])
def test_cli_confirmation_approved(
    affirmative: str,
    monkeypatch: pytest.MonkeyPatch,
    sample_context: ExecutionContext,
    sample_decision: SecurityDecision,
) -> None:
    """Verify affirmative user inputs approve the action."""
    monkeypatch.setattr("builtins.input", lambda _: affirmative)
    provider = CliConfirmationProvider()
    assert provider.request_confirmation(sample_context, sample_decision) is True


@pytest.mark.parametrize("declined", ["n", "N", "no", "NO", "", "   ", "cancel", "invalid"])
def test_cli_confirmation_declined(
    declined: str,
    monkeypatch: pytest.MonkeyPatch,
    sample_context: ExecutionContext,
    sample_decision: SecurityDecision,
) -> None:
    """Verify non-affirmative user inputs deny the action."""
    monkeypatch.setattr("builtins.input", lambda _: declined)
    provider = CliConfirmationProvider()
    assert provider.request_confirmation(sample_context, sample_decision) is False


def test_cli_confirmation_interrupted(
    monkeypatch: pytest.MonkeyPatch,
    sample_context: ExecutionContext,
    sample_decision: SecurityDecision,
) -> None:
    """Verify KeyboardInterrupt in CLI confirmation fails closed and returns False."""
    def raise_interrupt(_: str) -> str:
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", raise_interrupt)
    provider = CliConfirmationProvider()
    assert provider.request_confirmation(sample_context, sample_decision) is False


def test_non_interactive_confirmation_always_denies(
    sample_context: ExecutionContext,
    sample_decision: SecurityDecision,
) -> None:
    """Verify NonInteractiveConfirmationProvider always returns False."""
    provider = NonInteractiveConfirmationProvider()
    assert provider.request_confirmation(sample_context, sample_decision) is False


def test_confirmation_manager_no_provider_denies(
    sample_context: ExecutionContext,
    sample_decision: SecurityDecision,
) -> None:
    """Verify ConfirmationManager with no provider fails closed."""
    mgr = ConfirmationManager(provider=None)
    assert mgr.request_confirmation(sample_context, sample_decision) is False


def test_confirmation_manager_exception_fails_closed(
    sample_context: ExecutionContext,
    sample_decision: SecurityDecision,
) -> None:
    """Verify ConfirmationManager fails closed if provider raises an exception."""
    faulty_provider = MagicMock(spec=ConfirmationProvider)
    faulty_provider.request_confirmation.side_effect = RuntimeError("Broken UI")

    mgr = ConfirmationManager(provider=faulty_provider)
    assert mgr.request_confirmation(sample_context, sample_decision) is False
