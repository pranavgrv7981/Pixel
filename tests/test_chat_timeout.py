"""Tests for chat timeout behavior, streaming timeout protection, and error propagation."""

from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.core.config import Settings
from app.core.exceptions import OllamaConnectionError
from app.core.ollama_client import OllamaClient
from app.ui.worker import AgentWorker


def test_ollama_client_timeout_configuration() -> None:
    """Verify OllamaClient configures granular timeouts without early abort."""
    settings = Settings(
        ollama_timeout_seconds=300.0,
        ollama_connect_timeout_seconds=10.0,
        ollama_generation_timeout_seconds=600.0,
    )
    client = OllamaClient(settings=settings)
    assert client.timeout == 300.0
    assert client.settings.ollama_connect_timeout_seconds == 10.0
    assert client.settings.ollama_generation_timeout_seconds == 600.0


def test_agent_worker_streams_chunks_without_timeout() -> None:
    """Verify AgentWorker emits chunks and completes cleanly for long streaming responses."""
    agent = MagicMock(spec=Agent)
    agent.stream_run.return_value = iter(["Hello", " ", "world", "!"])

    worker = AgentWorker(agent=agent, prompt="hi", model="qwen3:30b")
    received_chunks: list[str] = []
    finished_responses: list[str] = []
    error_list: list[str] = []

    worker.chunk_received.connect(received_chunks.append)
    worker.finished.connect(finished_responses.append)
    worker.error_occurred.connect(error_list.append)

    worker.run()

    assert received_chunks == ["Hello", " ", "world", "!"]
    assert finished_responses == ["Hello world!"]
    assert len(error_list) == 0


def test_agent_worker_propagates_timeout_error() -> None:
    """Verify Ollama timeout exceptions are propagated cleanly to UI without crashing."""
    agent = MagicMock(spec=Agent)
    agent.stream_run.side_effect = OllamaConnectionError(
        "Streaming chat to Ollama timed out after 300.0s",
        details={"timeout": 300.0},
    )

    worker = AgentWorker(agent=agent, prompt="hi", model="qwen3:30b")
    error_list: list[str] = []
    worker.error_occurred.connect(error_list.append)

    worker.run()

    assert len(error_list) == 1
    assert "timed out after 300.0s" in error_list[0]


def test_worker_cancellation_is_distinct_from_timeout() -> None:
    """Verify user cancellation cleanly halts the worker without triggering timeout error."""
    agent = MagicMock(spec=Agent)

    def slow_generator(*args, **kwargs):
        yield "Chunk 1"
        worker.cancel()
        yield "Chunk 2"

    agent.stream_run.side_effect = slow_generator

    worker = AgentWorker(agent=agent, prompt="hi", model="qwen3:30b")
    received_chunks: list[str] = []
    finished_responses: list[str] = []
    error_list: list[str] = []

    worker.chunk_received.connect(received_chunks.append)
    worker.finished.connect(finished_responses.append)
    worker.error_occurred.connect(error_list.append)

    worker.run()

    assert received_chunks == ["Chunk 1"]
    assert finished_responses == ["Chunk 1"]
    assert len(error_list) == 0
