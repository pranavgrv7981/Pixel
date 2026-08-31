"""Tests for app/core/exceptions.py."""

import pytest

from app.core.exceptions import (
    AssistantError,
    ConfigurationError,
    ConversationError,
    ModelError,
    PermissionDeniedError,
    SecurityError,
    StorageError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)


def test_base_assistant_error() -> None:
    """Verify base AssistantError message and details formatting."""
    err = AssistantError("Basic error")
    assert str(err) == "Basic error"
    assert err.details == {}

    detailed_err = AssistantError("Failed action", details={"code": 404, "target": "item"})
    assert "Failed action" in str(detailed_err)
    assert "'code': 404" in str(detailed_err)
    assert detailed_err.details["target"] == "item"


@pytest.mark.parametrize(
    "exception_cls,parent_cls",
    [
        (ConfigurationError, AssistantError),
        (ModelError, AssistantError),
        (ConversationError, AssistantError),
        (ToolError, AssistantError),
        (ToolNotFoundError, ToolError),
        (ToolValidationError, ToolError),
        (ToolExecutionError, ToolError),
        (SecurityError, AssistantError),
        (PermissionDeniedError, SecurityError),
        (StorageError, AssistantError),
    ],
)
def test_exception_inheritance(exception_cls: type, parent_cls: type) -> None:
    """Verify exception hierarchy preserves domain inheritance."""
    inst = exception_cls("Test error message")
    assert isinstance(inst, parent_cls)
    assert isinstance(inst, AssistantError)
    assert isinstance(inst, Exception)
