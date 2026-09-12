"""Integration tests verifying the Agent Intelligence Decision Pipeline."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.core.config import Settings
from app.core.ollama_client import ModelResponse
from app.agent.intelligence_models import ActionType
from app.tools.demo import SafeCalculateTool, GetCurrentTimeTool
from app.tools.registry import ToolRegistry


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.default_model = "qwen3:30b"
    client.chat.return_value = ModelResponse(content="Calculated result is 100.", tool_calls=[])
    client.stream_chat.return_value = iter(["Recursion ", "is ", "a function ", "calling itself."])
    return client


@pytest.fixture
def agent(tmp_path: Path, mock_client: MagicMock) -> Agent:
    settings = Settings(
        autonomy_level="confirm_actions",
        quality_checks_enabled=True,
        quality_telemetry_enabled=True,
        default_model="qwen3:30b",
        enable_fast_path=False,
    )
    registry = ToolRegistry()
    registry.register(SafeCalculateTool())
    registry.register(GetCurrentTimeTool())
    return Agent(
        client=mock_client,
        registry=registry,
        settings=settings,
    )


def test_agent_run_clarification_pipeline(agent: Agent) -> None:
    # Ambiguous prompt -> returns clarification without calling LLM
    res = agent.run("Fix this")
    assert "clarify" in res.lower()
    assert agent.last_intent is not None
    assert agent.last_intent.action_type == ActionType.CLARIFICATION


def test_agent_stream_run_direct_answer_pipeline(agent: Agent, mock_client: MagicMock) -> None:
    # Explanatory prompt -> direct stream without tools
    tokens = list(agent.stream_run("Explain recursion"))
    assert "".join(tokens) == "Recursion is a function calling itself."
    assert agent.last_intent is not None
    assert agent.last_intent.action_type == ActionType.ANSWER
    assert mock_client.stream_chat.call_count == 1


def test_agent_run_tool_pipeline(agent: Agent, mock_client: MagicMock) -> None:
    res = agent.run("What is 25 * 4?")
    assert "Calculated result is 100" in res
    assert agent.last_intent is not None
    assert agent.last_intent.action_type == ActionType.TOOL
