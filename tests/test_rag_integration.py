"""End-to-end integration tests for RAG retrieval, agent orchestration, and citations."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.knowledge.manager import KnowledgeManager
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.manager import PermissionManager
from app.security.policies import SecurityPolicy
from app.tools.knowledge import SearchKnowledgeTool
from app.tools.path_guard import PathGuard
from app.tools.registry import ToolRegistry


@pytest.fixture
def rag_agent_env(tmp_path: Path) -> tuple[Agent, KnowledgeManager, MagicMock, Path]:
    allowed_dir = tmp_path / "sandbox"
    allowed_dir.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "knowledge.db"

    settings = Settings(
        filesystem_allowed_roots=[str(allowed_dir)],
        knowledge_database_path=str(db_file),
    )
    guard = PathGuard(settings=settings)
    km = KnowledgeManager(settings=settings, path_guard=guard)
    km.initialize()

    # Pre-index a test document
    doc_path = allowed_dir / "compiler_notes.txt"
    doc_path.write_text(
        "Compiler Notes: Lexical scope resolution binds identifier references "
        "to the nearest enclosing block or environment in the static abstract syntax tree.",
        encoding="utf-8",
    )
    km.index_file(doc_path)

    registry = ToolRegistry()
    registry.register(SearchKnowledgeTool(knowledge_manager=km, settings=settings))

    conf_mgr = ConfirmationManager(provider=MagicMock(spec=ConfirmationProvider))
    perm_mgr = PermissionManager(policy=SecurityPolicy(), confirmation_manager=conf_mgr)

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

    return agent, km, mock_client, allowed_dir


def test_agent_search_knowledge_and_grounded_answer(rag_agent_env: tuple) -> None:
    agent, km, mock_client, _ = rag_agent_env

    # Turn 1: Model issues search_knowledge tool call
    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "search_knowledge",
            "arguments": {"query": "lexical scope resolution"},
        }]),
        ModelResponse("According to compiler_notes.txt, lexical scope resolution binds identifiers to the nearest enclosing block."),
    ]

    reply = agent.run("What does my compiler notes say about lexical scope?")

    assert "compiler_notes.txt" in reply
    assert "lexical scope resolution" in reply
    assert mock_client.chat.call_count == 2


def test_agent_no_hit_response(rag_agent_env: tuple) -> None:
    agent, km, mock_client, _ = rag_agent_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "search_knowledge",
            "arguments": {"query": "quantum entanglement in superconducting qubits"},
        }]),
        ModelResponse("I could not find any information about quantum entanglement in your indexed notes."),
    ]

    reply = agent.run("What do my notes say about quantum entanglement?")
    assert "could not find" in reply
