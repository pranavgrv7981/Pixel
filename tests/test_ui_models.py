"""Unit tests for UI data models and state representations."""

from datetime import datetime, timezone
import pytest

from app.ui.models import (
    BackendStatus,
    ChatMessage,
    ConversationItem,
    MessageRole,
    ToolEvent,
    UIState,
)


def test_ui_state_enum_values() -> None:
    assert UIState.IDLE.value == "idle"
    assert UIState.THINKING.value == "thinking"
    assert UIState.STREAMING.value == "streaming"
    assert UIState.EXECUTING_TOOL.value == "executing_tool"
    assert UIState.AWAITING_CONFIRMATION.value == "awaiting_confirmation"
    assert UIState.ERROR.value == "error"


def test_message_role_enum_values() -> None:
    assert MessageRole.USER.value == "user"
    assert MessageRole.ASSISTANT.value == "assistant"
    assert MessageRole.SYSTEM.value == "system"
    assert MessageRole.TOOL.value == "tool"


def test_chat_message_creation() -> None:
    msg = ChatMessage(
        id="msg-1",
        role=MessageRole.USER,
        content="Hello assistant",
    )
    assert msg.id == "msg-1"
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello assistant"
    assert isinstance(msg.timestamp, datetime)
    assert msg.is_streaming is False


def test_tool_event_tracking() -> None:
    event = ToolEvent(
        tool_name="read_text_file",
        risk_level="READ",
        status="running",
        summary="Reading file",
    )
    assert event.tool_name == "read_text_file"
    assert event.risk_level == "READ"
    assert event.status == "running"


def test_backend_status_defaults() -> None:
    status = BackendStatus()
    assert status.ollama_connected is False
    assert status.tools_count == 58
    assert status.security_active is True
    assert status.docs_count == 0

