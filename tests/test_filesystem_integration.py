"""End-to-end integration tests combining Agent, ToolRegistry, PermissionManager, and Filesystem tools."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation, Role
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.manager import PermissionManager
from app.security.policies import SecurityPolicy
from app.tools.filesystem import (
    CreateFileTool,
    DeleteFileTool,
    ListDirectoryTool,
    ReadTextFileTool,
    WriteTextFileTool,
)
from app.tools.path_guard import PathGuard
from app.tools.registry import ToolRegistry


@pytest.fixture
def agent_env(tmp_path: Path) -> tuple[Agent, Path, MagicMock, MagicMock]:
    """Provide a fully configured Agent environment bound to a temporary sandbox."""
    sandbox = tmp_path / "agent_sandbox"
    sandbox.mkdir()

    settings = Settings(
        project_root=tmp_path,
        data_dir=sandbox,
        logs_dir=tmp_path / "logs",
        filesystem_allowed_roots=[str(sandbox)],
    )

    guard = PathGuard(settings=settings, allowed_roots=[sandbox], protected_paths=[])
    registry = ToolRegistry()
    registry.register(ListDirectoryTool(path_guard=guard, settings=settings))
    registry.register(ReadTextFileTool(path_guard=guard, settings=settings))
    registry.register(CreateFileTool(path_guard=guard, settings=settings))
    registry.register(WriteTextFileTool(path_guard=guard, settings=settings))
    registry.register(DeleteFileTool(path_guard=guard, settings=settings))

    conf_provider = MagicMock(spec=ConfirmationProvider)
    conf_mgr = ConfirmationManager(provider=conf_provider)
    policy = SecurityPolicy()
    perm_mgr = PermissionManager(policy=policy, confirmation_manager=conf_mgr)

    mock_client = MagicMock(spec=OllamaClient)
    mock_client.base_url = "http://localhost:11434"
    mock_client.default_model = "llama3"
    mock_client.check_connection.return_value = True
    mock_client.model_exists.return_value = True

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
        settings=settings,
    )

    return agent, sandbox, mock_client, conf_provider


def test_agent_read_tool_auto_approved(agent_env: tuple[Agent, Path, MagicMock, MagicMock]) -> None:
    """Verify READ filesystem operations execute automatically without confirmation."""
    agent, sandbox, mock_client, conf_provider = agent_env

    # Create dummy file to read
    (sandbox / "info.txt").write_text("Hello from file", encoding="utf-8")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "read_text_file", "arguments": {"path": "info.txt"}}]),
        ModelResponse("The file content is 'Hello from file'."),
    ]

    reply = agent.run("Read info.txt")
    assert reply == "The file content is 'Hello from file'."
    assert not conf_provider.request_confirmation.called


def test_agent_create_file_auto_approved(agent_env: tuple[Agent, Path, MagicMock, MagicMock]) -> None:
    """Verify LOW risk creation operations execute automatically."""
    agent, sandbox, mock_client, conf_provider = agent_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "create_file", "arguments": {"path": "new.txt", "content": "fresh"}}]),
        ModelResponse("File created."),
    ]

    reply = agent.run("Create new.txt with fresh content")
    assert reply == "File created."
    assert (sandbox / "new.txt").exists()
    assert (sandbox / "new.txt").read_text(encoding="utf-8") == "fresh"
    assert not conf_provider.request_confirmation.called


def test_agent_delete_file_approved_by_user(agent_env: tuple[Agent, Path, MagicMock, MagicMock]) -> None:
    """Verify HIGH risk delete_file prompts confirmation and deletes file if user approves."""
    agent, sandbox, mock_client, conf_provider = agent_env
    conf_provider.request_confirmation.return_value = True

    target = sandbox / "to_be_deleted.txt"
    target.write_text("trash", encoding="utf-8")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "delete_file", "arguments": {"path": "to_be_deleted.txt"}}]),
        ModelResponse("File was successfully deleted."),
    ]

    reply = agent.run("Delete to_be_deleted.txt")
    assert reply == "File was successfully deleted."
    assert conf_provider.request_confirmation.called
    assert not target.exists()


def test_agent_delete_file_declined_by_user(agent_env: tuple[Agent, Path, MagicMock, MagicMock]) -> None:
    """Verify HIGH risk delete_file prompts confirmation and skips deletion if user declines."""
    agent, sandbox, mock_client, conf_provider = agent_env
    conf_provider.request_confirmation.return_value = False

    target = sandbox / "protected_user_file.txt"
    target.write_text("important data", encoding="utf-8")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "delete_file", "arguments": {"path": "protected_user_file.txt"}}]),
        ModelResponse("I did not delete the file since you declined."),
    ]

    reply = agent.run("Delete protected_user_file.txt")
    assert reply == "I did not delete the file since you declined."
    assert conf_provider.request_confirmation.called
    assert target.exists()  # Crucial: File remains intact!
    assert target.read_text(encoding="utf-8") == "important data"


def test_agent_path_traversal_blocked(agent_env: tuple[Agent, Path, MagicMock, MagicMock]) -> None:
    """Verify path traversal requested by LLM tool call is blocked by PathGuard and safe denial is returned."""
    agent, sandbox, mock_client, conf_provider = agent_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "read_text_file", "arguments": {"path": "../../../system_file.txt"}}]),
        ModelResponse("I cannot access files outside your workspace."),
    ]

    reply = agent.run("Read system file")
    assert reply == "I cannot access files outside your workspace."
    assert not conf_provider.request_confirmation.called

    msgs = agent.conversation.get_messages()
    assert msgs[2].role == Role.TOOL
    assert "outside allowed directory boundaries" in msgs[2].content
