"""Integration tests for Agent and ContextManager collaboration."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.core.config import Settings
from app.core.ollama_client import ModelResponse
from app.context.database import ContextDatabase
from app.context.manager import ContextManager


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.default_model = "qwen3:30b"
    client.chat.return_value = ModelResponse(
        content="Context-aware answer: 25 * 4 = 100.",
        tool_calls=[],
    )
    client.stream_chat.return_value = iter(["Context-aware ", "streaming ", "answer."])
    return client


@pytest.fixture
def agent_with_context(tmp_path: Path, mock_client: MagicMock) -> Agent:
    db = ContextDatabase(db_path=tmp_path / "test_agent_ctx.db")
    db.initialize()
    settings = Settings(
        context_management_enabled=True,
        default_model="qwen3:30b",
        enable_fast_path=False,
    )
    ctx_mgr = ContextManager(db=db, settings=settings)
    return Agent(
        client=mock_client,
        context_manager=ctx_mgr,
        settings=settings,
    )


def test_agent_run_invokes_context_manager(agent_with_context: Agent, mock_client: MagicMock) -> None:
    res = agent_with_context.run("What is 25 * 4?")
    assert "25 * 4 = 100" in res
    assert mock_client.chat.call_count == 1
    args, kwargs = mock_client.chat.call_args
    payload = args[0]
    # Check payload structured by ContextManager
    assert any(m["role"] == "system" for m in payload)
    assert payload[-1]["role"] == "user"
    assert payload[-1]["content"] == "What is 25 * 4?"


def test_agent_stream_run_invokes_context_manager(agent_with_context: Agent, mock_client: MagicMock) -> None:
    chunks = list(agent_with_context.stream_run("Hello streaming"))
    assert "".join(chunks) == "Context-aware streaming answer."
    assert mock_client.stream_chat.call_count == 1
    args, kwargs = mock_client.stream_chat.call_args
    payload = args[0]
    assert payload[-1]["role"] == "user"
    assert payload[-1]["content"] == "Hello streaming"
