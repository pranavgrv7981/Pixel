"""End-to-end integration tests for persistent memory, agent orchestration, and session restarts."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation, ConversationManager
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.memory.manager import MemoryManager
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.manager import PermissionManager
from app.security.policies import SecurityPolicy
from app.tools.memory import (
    ForgetMemoryTool,
    RecallMemoryTool,
    RememberMemoryTool,
)
from app.tools.registry import ToolRegistry


@pytest.fixture
def memory_agent_env(tmp_path: Path) -> tuple[Agent, MemoryManager, MagicMock, MagicMock, Path]:
    db_file = tmp_path / "test_persist.db"
    settings = Settings(memory_database_path=str(db_file), enable_fast_path=False)
    mgr = MemoryManager(settings=settings)
    mgr.initialize()

    registry = ToolRegistry()
    registry.register(RememberMemoryTool(memory_manager=mgr, settings=settings))
    registry.register(RecallMemoryTool(memory_manager=mgr, settings=settings))
    registry.register(ForgetMemoryTool(memory_manager=mgr, settings=settings))

    conf_provider = MagicMock(spec=ConfirmationProvider)
    conf_mgr = ConfirmationManager(provider=conf_provider)
    policy = SecurityPolicy()
    perm_mgr = PermissionManager(policy=policy, confirmation_manager=conf_mgr)

    mock_client = MagicMock(spec=OllamaClient)
    mock_client.base_url = "http://localhost:11434"
    mock_client.default_model = "llama3"
    mock_client.check_connection.return_value = True
    mock_client.model_exists.return_value = True

    conv = Conversation(repository=mgr.conversations)
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
        memory_manager=mgr,
        settings=settings,
    )

    return agent, mgr, mock_client, conf_provider, db_file


def test_agent_remember_and_recall_integration(
    memory_agent_env: tuple[Agent, MemoryManager, MagicMock, MagicMock, Path]
) -> None:
    agent, mgr, mock_client, conf_provider, _ = memory_agent_env

    # 1. Model issues remember_memory tool call
    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "remember_memory",
            "arguments": {"category": "PROJECT", "key": "main_project", "value": "Atlas", "importance": 8},
        }]),
        ModelResponse("I will remember that your main project is Atlas."),
    ]

    reply = agent.run("Remember that my main project is Atlas.")
    assert "remember that your main project is Atlas" in reply
    # remember_memory is LOW risk: auto-executes without prompting confirmation
    assert not conf_provider.request_confirmation.called

    # Verify memory is stored in SQLite
    recalled = mgr.recall(query="Atlas")
    assert len(recalled) == 1
    assert recalled[0].key == "main_project"
    assert recalled[0].value == "Atlas"


def test_agent_forget_memory_confirmed_by_user(
    memory_agent_env: tuple[Agent, MemoryManager, MagicMock, MagicMock, Path]
) -> None:
    agent, mgr, mock_client, conf_provider, _ = memory_agent_env
    conf_provider.request_confirmation.return_value = True

    # Pre-seed memory
    mgr.remember("PROJECT", "old_project", "Titan")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "forget_memory",
            "arguments": {"key": "old_project"},
        }]),
        ModelResponse("I have forgotten about old_project."),
    ]

    reply = agent.run("Forget about old_project")
    assert "forgotten about old_project" in reply
    assert conf_provider.request_confirmation.called
    assert mgr.recall(query="Titan") == []


def test_agent_forget_memory_declined_by_user(
    memory_agent_env: tuple[Agent, MemoryManager, MagicMock, MagicMock, Path]
) -> None:
    agent, mgr, mock_client, conf_provider, _ = memory_agent_env
    conf_provider.request_confirmation.return_value = False

    # Pre-seed memory
    mgr.remember("PROJECT", "preserved_project", "Pegasus")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "forget_memory",
            "arguments": {"key": "preserved_project"},
        }]),
        ModelResponse("Memory was not deleted."),
    ]

    reply = agent.run("Forget about preserved_project")
    assert reply == "Memory was not deleted."
    assert conf_provider.request_confirmation.called
    # Memory must still be in SQLite because user declined
    assert len(mgr.recall(query="Pegasus")) == 1


def test_persistence_across_simulated_restart(
    memory_agent_env: tuple[Agent, MemoryManager, MagicMock, MagicMock, Path]
) -> None:
    agent_s1, mgr_s1, mock_client_s1, _, db_file = memory_agent_env

    # Session 1: User tells assistant to remember fact
    mock_client_s1.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "remember_memory",
            "arguments": {"category": "PROJECT", "key": "main_project", "value": "Atlas"},
        }]),
        ModelResponse("Stored main_project as Atlas."),
    ]
    agent_s1.run("Remember that my main project is Atlas.")

    # --- SIMULATE APPLICATION RESTART ---
    # Session 2: completely new instances connecting to the same SQLite db_file
    settings_s2 = Settings(memory_database_path=str(db_file), enable_fast_path=False)
    mgr_s2 = MemoryManager(settings=settings_s2)
    mgr_s2.initialize()

    registry_s2 = ToolRegistry()
    registry_s2.register(RememberMemoryTool(memory_manager=mgr_s2, settings=settings_s2))
    registry_s2.register(RecallMemoryTool(memory_manager=mgr_s2, settings=settings_s2))
    registry_s2.register(ForgetMemoryTool(memory_manager=mgr_s2, settings=settings_s2))

    conf_mgr_s2 = ConfirmationManager(provider=MagicMock())
    perm_mgr_s2 = PermissionManager(policy=SecurityPolicy(), confirmation_manager=conf_mgr_s2)
    mock_client_s2 = MagicMock(spec=OllamaClient)
    mock_client_s2.base_url = "http://localhost:11434"
    mock_client_s2.default_model = "llama3"

    # In Session 2, model directly answers using injected persistent memory context
    mock_client_s2.chat.return_value = ModelResponse("Your main project is Atlas.")

    conv_s2 = Conversation(repository=mgr_s2.conversations)
    agent_s2 = Agent(
        conversation=conv_s2,
        client=mock_client_s2,
        registry=registry_s2,
        permission_manager=perm_mgr_s2,
        memory_manager=mgr_s2,
        settings=settings_s2,
    )

    reply_s2 = agent_s2.run("What is my main project?")
    assert reply_s2 == "Your main project is Atlas."

    # Inspect payload passed to mock_client_s2
    sent_payload = mock_client_s2.chat.call_args[0][0]
    system_msg = [m for m in sent_payload if m["role"] == "system"][0]
    assert "[Persistent User Context & Memories]" in system_msg["content"]
    assert "[PROJECT] main_project: Atlas" in system_msg["content"]
