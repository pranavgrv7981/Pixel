"""Tests for app/agent/agent.py with mocked OllamaClient."""

from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation, Role
from app.core.config import Settings
from app.core.exceptions import InvalidMessageError, ToolRoundLimitError
from app.core.ollama_client import ModelResponse, OllamaClient
from app.tools.demo import GetCurrentTimeTool, SafeCalculateTool
from app.tools.registry import ToolRegistry


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Fixture providing a ToolRegistry populated with demo tools."""
    registry = ToolRegistry()
    registry.register(GetCurrentTimeTool())
    registry.register(SafeCalculateTool())
    return registry


@pytest.fixture
def mock_client() -> MagicMock:
    """Fixture providing a mocked OllamaClient."""
    client = MagicMock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.default_model = "llama3"
    client.check_connection.return_value = True
    client.model_exists.return_value = True
    return client


def test_agent_run_direct_response(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify agent returns direct response when no tool calls are requested."""
    mock_client.chat.return_value = ModelResponse("Paris is the capital of France.")
    conv = Conversation()
    agent = Agent(conversation=conv, client=mock_client, registry=tool_registry)

    reply = agent.run("What is the capital of France?")
    assert reply == "Paris is the capital of France."
    assert conv.message_count() == 2  # user + assistant
    assert conv.get_messages()[1].content == "Paris is the capital of France."


def test_agent_run_single_tool_call(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify agent executes a tool call and synthesizes a final answer."""
    # Round 1: Model requests get_current_time
    tool_call_response = ModelResponse(
        "",
        tool_calls=[{"name": "get_current_time", "arguments": {"format": "%Y-%m-%d"}}],
    )
    # Round 2: Model returns final answer after receiving tool result
    final_response = ModelResponse("Today's date is 2026-08-30.")
    mock_client.chat.side_effect = [tool_call_response, final_response]

    conv = Conversation()
    agent = Agent(conversation=conv, client=mock_client, registry=tool_registry, settings=Settings(enable_fast_path=False))

    reply = agent.run("What is today's date?")
    assert reply == "Today's date is 2026-08-30."

    # History: User -> Assistant (tool_call) -> Tool (result) -> Assistant (final)
    assert conv.message_count() == 4
    msgs = conv.get_messages()
    assert msgs[0].role == Role.USER
    assert msgs[1].role == Role.ASSISTANT
    assert msgs[1].tool_calls is not None
    assert msgs[2].role == Role.TOOL
    assert "current_time" in msgs[2].content
    assert msgs[3].role == Role.ASSISTANT
    assert msgs[3].content == "Today's date is 2026-08-30."


def test_agent_run_multiple_tool_rounds(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify agent handles sequential tool calls across multiple rounds."""
    # Round 1: calls get_current_time
    round1 = ModelResponse("", tool_calls=[{"name": "get_current_time", "arguments": {}}])
    # Round 2: calls calculate
    round2 = ModelResponse("", tool_calls=[{"name": "calculate", "arguments": {"expression": "10 * 5"}}])
    # Round 3: final answer
    round3 = ModelResponse("Current time retrieved and 10 * 5 is 50.")
    mock_client.chat.side_effect = [round1, round2, round3]

    conv = Conversation()
    agent = Agent(conversation=conv, client=mock_client, registry=tool_registry)

    reply = agent.run("Get time and multiply 10 by 5")
    assert reply == "Current time retrieved and 10 * 5 is 50."
    assert conv.message_count() == 6  # User + R1 + T1 + R2 + T2 + R3


def test_agent_run_unknown_tool_handling(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify agent handles model requesting an unregistered tool gracefully."""
    # Round 1: Model requests unknown tool
    round1 = ModelResponse("", tool_calls=[{"name": "non_existent_tool", "arguments": {}}])
    # Round 2: Model recognizes failure and replies
    round2 = ModelResponse("I could not perform that action.")
    mock_client.chat.side_effect = [round1, round2]

    conv = Conversation()
    agent = Agent(conversation=conv, client=mock_client, registry=tool_registry)

    reply = agent.run("Do something impossible")
    assert reply == "I could not perform that action."

    msgs = conv.get_messages()
    assert msgs[2].role == Role.TOOL
    assert "not found in registry" in msgs[2].content


def test_agent_run_max_rounds_enforced(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify ToolRoundLimitError is raised when model loops indefinitely."""
    # Infinite tool loop
    infinite_tool_response = ModelResponse("", tool_calls=[{"name": "get_current_time", "arguments": {}}])
    mock_client.chat.return_value = infinite_tool_response

    conv = Conversation()
    agent = Agent(conversation=conv, client=mock_client, registry=tool_registry, max_rounds=3)

    with pytest.raises(ToolRoundLimitError) as exc_info:
        agent.run("Infinite loop")
    assert "Exceeded maximum tool-call rounds limit" in str(exc_info.value)


def test_agent_stream_run_direct(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify stream_run yields final answer chunks."""
    mock_client.chat.return_value = ModelResponse("Direct streaming answer")

    conv = Conversation()
    agent = Agent(conversation=conv, client=mock_client, registry=tool_registry)

    stream = agent.stream_run("Hello")
    output = "".join(list(stream))
    assert output == "Direct streaming answer"
    assert conv.message_count() == 2


def test_agent_stream_run_with_tool(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify stream_run executes tools and yields final answer."""
    round1 = ModelResponse("", tool_calls=[{"name": "calculate", "arguments": {"expression": "2 + 2"}}])
    round2 = ModelResponse("The result is 4.")
    mock_client.chat.side_effect = [round1, round2]

    conv = Conversation()
    agent = Agent(conversation=conv, client=mock_client, registry=tool_registry, settings=Settings(enable_fast_path=False))

    stream = agent.stream_run("Calculate 2 + 2")
    output = "".join(list(stream))
    assert output == "The result is 4."
    assert conv.message_count() == 4


def test_agent_empty_prompt_rejection(mock_client: MagicMock, tool_registry: ToolRegistry) -> None:
    """Verify agent rejects empty and whitespace-only prompts."""
    agent = Agent(client=mock_client, registry=tool_registry)

    with pytest.raises(InvalidMessageError):
        agent.run("")

    with pytest.raises(InvalidMessageError):
        agent.run("   ")
