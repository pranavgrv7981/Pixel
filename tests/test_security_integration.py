"""End-to-end integration tests for security enforcement, confirmations, and fail-closed behaviors."""

from typing import Any
from unittest.mock import MagicMock
from pydantic import BaseModel, Field
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation, Role
from app.core.ollama_client import ModelResponse, OllamaClient
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.manager import PermissionManager
from app.security.permissions import (
    ExecutionContext,
    PermissionDecision,
    SecurityDecision,
)
from app.security.policies import SecurityPolicy
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.registry import ToolRegistry


class TrackedArgs(BaseModel):
    command: str = Field(description="Command string")


class TrackedExecutionTool(Tool):
    """Tool that tracks how many times its internal _run method was invoked."""

    def __init__(self, name: str, risk_level: RiskLevel) -> None:
        super().__init__(
            name=name,
            description="Tool tracking execution attempts.",
            risk_level=risk_level,
            args_model=TrackedArgs,
        )
        self.execution_count: int = 0

    def _run(self, args: dict[str, Any]) -> ToolResult:
        self.execution_count += 1
        return ToolResult(success=True, data={"command": args["command"], "executed": True})


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.default_model = "llama3"
    client.check_connection.return_value = True
    client.model_exists.return_value = True
    return client


def test_allowed_tool_executes_once(mock_client: MagicMock) -> None:
    """Verify that an auto-approved tool (READ/LOW) executes exactly once."""
    tool = TrackedExecutionTool(name="read_tool", risk_level=RiskLevel.READ)
    registry = ToolRegistry()
    registry.register(tool)

    policy = SecurityPolicy()
    perm_mgr = PermissionManager(policy=policy)

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "read_tool", "arguments": {"command": "test"}}]),
        ModelResponse("Execution finished."),
    ]

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
    )

    reply = agent.run("Run read tool")
    assert reply == "Execution finished."
    assert tool.execution_count == 1
    assert conv.message_count() == 4
    msgs = conv.get_messages()
    assert msgs[2].role == Role.TOOL
    assert '"executed": true' in msgs[2].content


def test_denied_tool_never_executes(mock_client: MagicMock) -> None:
    """Verify that a prohibited tool (e.g. CRITICAL) is never executed."""
    tool = TrackedExecutionTool(name="critical_tool", risk_level=RiskLevel.CRITICAL)
    registry = ToolRegistry()
    registry.register(tool)

    policy = SecurityPolicy(allow_critical=False)
    perm_mgr = PermissionManager(policy=policy)

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "critical_tool", "arguments": {"command": "wipe"}}]),
        ModelResponse("Operation was blocked by safety policy."),
    ]

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
    )

    reply = agent.run("Run critical tool")
    assert reply == "Operation was blocked by safety policy."
    assert tool.execution_count == 0  # Crucial security guarantee: execution_count remains 0!

    msgs = conv.get_messages()
    assert msgs[2].role == Role.TOOL
    assert "Tool execution denied by safety policy" in msgs[2].content


def test_confirmation_approved_executes_once(mock_client: MagicMock) -> None:
    """Verify MEDIUM risk tool requiring confirmation executes once when approved."""
    tool = TrackedExecutionTool(name="medium_tool", risk_level=RiskLevel.MEDIUM)
    registry = ToolRegistry()
    registry.register(tool)

    approving_provider = MagicMock(spec=ConfirmationProvider)
    approving_provider.request_confirmation.return_value = True
    conf_mgr = ConfirmationManager(provider=approving_provider)

    policy = SecurityPolicy()
    perm_mgr = PermissionManager(policy=policy, confirmation_manager=conf_mgr)

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "medium_tool", "arguments": {"command": "modify"}}]),
        ModelResponse("Modification completed."),
    ]

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
    )

    reply = agent.run("Modify something")
    assert reply == "Modification completed."
    assert approving_provider.request_confirmation.called
    assert tool.execution_count == 1


def test_confirmation_denied_never_executes(mock_client: MagicMock) -> None:
    """Verify MEDIUM risk tool requiring confirmation NEVER executes when declined by user."""
    tool = TrackedExecutionTool(name="medium_tool", risk_level=RiskLevel.MEDIUM)
    registry = ToolRegistry()
    registry.register(tool)

    denying_provider = MagicMock(spec=ConfirmationProvider)
    denying_provider.request_confirmation.return_value = False
    conf_mgr = ConfirmationManager(provider=denying_provider)

    policy = SecurityPolicy()
    perm_mgr = PermissionManager(policy=policy, confirmation_manager=conf_mgr)

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "medium_tool", "arguments": {"command": "modify"}}]),
        ModelResponse("I understand you declined the action."),
    ]

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
    )

    reply = agent.run("Modify something")
    assert reply == "I understand you declined the action."
    assert denying_provider.request_confirmation.called
    assert tool.execution_count == 0  # Never invoked


def test_invalid_arguments_do_not_reach_execution(mock_client: MagicMock) -> None:
    """Verify that invalid arguments are rejected before permission or execution."""
    tool = TrackedExecutionTool(name="strict_tool", risk_level=RiskLevel.LOW)
    registry = ToolRegistry()
    registry.register(tool)

    perm_mgr = MagicMock(spec=PermissionManager)

    # Missing required argument 'command'
    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "strict_tool", "arguments": {}}]),
        ModelResponse("Invalid arguments provided."),
    ]

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
    )

    agent.run("Call tool with no args")
    assert tool.execution_count == 0
    assert not perm_mgr.request_permission.called


def test_permission_manager_internal_error_fails_closed(mock_client: MagicMock) -> None:
    """Verify that an internal error in PermissionManager fails closed (denies execution)."""
    tool = TrackedExecutionTool(name="safe_tool", risk_level=RiskLevel.LOW)
    registry = ToolRegistry()
    registry.register(tool)

    perm_mgr = PermissionManager()
    # Inject failure into policy evaluation
    perm_mgr.policy.evaluate = MagicMock(side_effect=RuntimeError("Database corruption"))

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "safe_tool", "arguments": {"command": "run"}}]),
        ModelResponse("Security failure prevented execution."),
    ]

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
    )

    reply = agent.run("Execute safe tool")
    assert reply == "Security failure prevented execution."
    assert tool.execution_count == 0  # Crucial: Failed closed!
