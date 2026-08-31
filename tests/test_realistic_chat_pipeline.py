"""Unit and integration regression tests for realistic GUI chat streaming and num_ctx safety."""

from unittest.mock import MagicMock
import pytest
from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.models.availability import ModelAvailabilityChecker
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry


def test_ollama_client_stream_chat_passes_num_ctx():
    """Verify OllamaClient.stream_chat passes options with num_ctx and keep_alive."""
    settings = Settings(ollama_num_ctx=2048, ollama_keep_alive="10m")
    client = OllamaClient(settings=settings)
    client._client = MagicMock()
    client._client.chat.return_value = iter([{"message": {"content": "Hello"}}])

    chunks = list(client.stream_chat([{"role": "user", "content": "hi"}], model="qwen3:30b"))

    assert chunks == ["Hello"]
    client._client.chat.assert_called_once()
    called_kwargs = client._client.chat.call_args[1]
    assert called_kwargs.get("model") == "qwen3:30b"
    assert called_kwargs.get("stream") is True
    assert called_kwargs.get("options") == {"num_ctx": 2048}
    assert called_kwargs.get("keep_alive") == "10m"


def test_agent_stream_run_direct_answer():
    """Verify Agent.stream_run yields all streamed chunks directly for conversational queries."""
    settings = Settings(ollama_num_ctx=2048)
    client = MagicMock(spec=OllamaClient)
    client.default_model = "qwen3:30b"
    client.stream_chat.return_value = ["Hello", " world", "!"]

    conv = Conversation()
    tool_reg = ToolRegistry()
    perm_mgr = PermissionManager(settings=settings)
    model_reg = ModelRegistry(settings=settings)
    avail = MagicMock(spec=ModelAvailabilityChecker)
    avail.list_installed_models.return_value = ["qwen3:30b"]
    avail._model_matches.return_value = True
    router = ModelRouter(registry=model_reg, availability_checker=avail, settings=settings)

    agent = Agent(
        client=client,
        conversation=conv,
        registry=tool_reg,
        permission_manager=perm_mgr,
        router=router,
        settings=settings,
    )

    chunks = list(agent.stream_run("hi"))
    assert "".join(chunks) == "Hello world!"
