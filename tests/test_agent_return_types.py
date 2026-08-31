"""Regression tests asserting strict return types for Agent.run and Agent.stream_run."""

from typing import Iterator
from unittest.mock import MagicMock
import pytest
from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient


def test_agent_run_returns_str():
    """Verify Agent.run strictly returns str."""
    client = MagicMock(spec=OllamaClient)
    client.default_model = "qwen3:30b"
    client.chat.return_value = ModelResponse("Response string")

    agent = Agent(
        client=client,
        conversation=Conversation(),
        settings=Settings(),
    )

    result = agent.run("hi")
    assert isinstance(result, str)
    assert result == "Response string"


def test_agent_stream_run_returns_iterator():
    """Verify Agent.stream_run strictly yields string tokens."""
    client = MagicMock(spec=OllamaClient)
    client.default_model = "qwen3:30b"
    client.stream_chat.return_value = iter(["Token1", "Token2"])

    agent = Agent(
        client=client,
        conversation=Conversation(),
        settings=Settings(),
    )

    gen = agent.stream_run("hi")
    assert hasattr(gen, "__iter__")
    assert hasattr(gen, "__next__")

    collected = list(gen)
    assert all(isinstance(t, str) for t in collected)
    assert collected == ["Token1", "Token2"]
