"""End-to-end integration tests combining Agent, ToolRegistry, PermissionManager, and System/Application tools."""

from unittest.mock import MagicMock, patch
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation, Role
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.manager import PermissionManager
from app.security.policies import SecurityPolicy
from app.tools.applications import (
    ApplicationRegistry,
    CloseApplicationTool,
    IsApplicationRunningTool,
    OpenApplicationTool,
)
from app.tools.registry import ToolRegistry
from app.tools.system import (
    GetMemoryUsageTool,
    ListRunningProcessesTool,
    SystemProvider,
)


@pytest.fixture
def agent_system_env() -> tuple[Agent, MagicMock, MagicMock, MagicMock]:
    settings = Settings()
    mock_sys_provider = MagicMock(spec=SystemProvider)
    mock_sys_provider.get_memory_usage.return_value = {
        "usage_percent": 45.0,
        "total_gb": 16.0,
        "used_gb": 7.2,
    }
    mock_sys_provider.list_processes.return_value = [
        {"pid": 1111, "name": "notepad.exe"}
    ]

    app_registry = ApplicationRegistry()
    registry = ToolRegistry()
    registry.register(GetMemoryUsageTool(provider=mock_sys_provider, settings=settings))
    registry.register(ListRunningProcessesTool(provider=mock_sys_provider, settings=settings))
    registry.register(OpenApplicationTool(registry=app_registry, system_provider=mock_sys_provider, settings=settings))
    registry.register(CloseApplicationTool(registry=app_registry, system_provider=mock_sys_provider, settings=settings))
    registry.register(IsApplicationRunningTool(registry=app_registry, system_provider=mock_sys_provider, settings=settings))

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

    return agent, mock_client, conf_provider, mock_sys_provider


def test_agent_system_read_auto_approved(
    agent_system_env: tuple[Agent, MagicMock, MagicMock, MagicMock]
) -> None:
    """Verify READ system metrics execute automatically without confirmation."""
    agent, mock_client, conf_provider, _ = agent_system_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "get_memory_usage", "arguments": {}}]),
        ModelResponse("RAM usage is currently 45%."),
    ]

    reply = agent.run("What is my RAM usage?")
    assert reply == "RAM usage is currently 45%."
    assert not conf_provider.request_confirmation.called


def test_agent_open_app_auto_approved(
    agent_system_env: tuple[Agent, MagicMock, MagicMock, MagicMock]
) -> None:
    """Verify LOW-risk open_application executes automatically without confirmation."""
    agent, mock_client, conf_provider, _ = agent_system_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "open_application", "arguments": {"app_name": "notepad"}}]),
        ModelResponse("Notepad has been opened."),
    ]

    with patch("shutil.which", return_value="C:\\Windows\\notepad.exe"), \
         patch("subprocess.Popen") as mock_popen:
        reply = agent.run("Open notepad")
        assert reply == "Notepad has been opened."
        assert not conf_provider.request_confirmation.called
        assert mock_popen.called


def test_agent_close_app_confirmed_by_user(
    agent_system_env: tuple[Agent, MagicMock, MagicMock, MagicMock]
) -> None:
    """Verify MEDIUM-risk close_application prompts confirmation and closes if approved."""
    agent, mock_client, conf_provider, mock_sys_provider = agent_system_env
    conf_provider.request_confirmation.return_value = True

    mock_sys_provider.list_processes.side_effect = [
        [{"pid": 1111, "name": "notepad.exe"}],
        [],  # Exited on verification
    ]

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "close_application", "arguments": {"app_name": "notepad"}}]),
        ModelResponse("Notepad was closed."),
    ]

    with patch("subprocess.run") as mock_run:
        reply = agent.run("Close notepad")
        assert reply == "Notepad was closed."
        assert conf_provider.request_confirmation.called
        assert mock_run.called


def test_agent_close_app_declined_by_user(
    agent_system_env: tuple[Agent, MagicMock, MagicMock, MagicMock]
) -> None:
    """Verify MEDIUM-risk close_application prompts confirmation and aborts if declined."""
    agent, mock_client, conf_provider, _ = agent_system_env
    conf_provider.request_confirmation.return_value = False

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "close_application", "arguments": {"app_name": "notepad"}}]),
        ModelResponse("I did not close Notepad since you cancelled the action."),
    ]

    with patch("subprocess.run") as mock_run:
        reply = agent.run("Close notepad")
        assert reply == "I did not close Notepad since you cancelled the action."
        assert conf_provider.request_confirmation.called
        assert not mock_run.called


def test_agent_arbitrary_app_rejected_before_confirmation(
    agent_system_env: tuple[Agent, MagicMock, MagicMock, MagicMock]
) -> None:
    """Verify unauthorized application names are rejected during argument validation before confirmation."""
    agent, mock_client, conf_provider, _ = agent_system_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "open_application", "arguments": {"app_name": "powershell.exe"}}]),
        ModelResponse("I cannot open unauthorized applications."),
    ]

    with patch("subprocess.Popen") as mock_popen:
        reply = agent.run("Open powershell")
        assert reply == "I cannot open unauthorized applications."
        assert not conf_provider.request_confirmation.called
        assert not mock_popen.called

    msgs = agent.conversation.get_messages()
    assert msgs[2].role == Role.TOOL
    assert "not in the approved whitelist" in msgs[2].content
