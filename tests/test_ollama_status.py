"""Tests for Ollama status and health reporting."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.core.ollama_client import (
    ChatMessage,
    ModelStatus,
    OllamaClient,
    OllamaStatus,
    ServerStatus,
)


def test_chat_message_serialization() -> None:
    """Verify ChatMessage converts properly to dictionary."""
    msg = ChatMessage(role="system", content="You are a helpful assistant.")
    assert msg.to_dict() == {"role": "system", "content": "You are a helpful assistant."}


def test_ollama_status_properties() -> None:
    """Verify boolean helper properties on OllamaStatus."""
    connected_available = OllamaStatus(
        server_status=ServerStatus.CONNECTED,
        model_status=ModelStatus.AVAILABLE,
        base_url="http://localhost:11434",
        model_name="llama3",
        available_models=["llama3:latest"],
    )
    assert connected_available.is_connected is True
    assert connected_available.is_model_available is True

    connected_missing = OllamaStatus(
        server_status=ServerStatus.CONNECTED,
        model_status=ModelStatus.NOT_AVAILABLE,
        base_url="http://localhost:11434",
        model_name="qwen:7b",
        available_models=["llama3:latest"],
    )
    assert connected_missing.is_connected is True
    assert connected_missing.is_model_available is False

    disconnected = OllamaStatus(
        server_status=ServerStatus.DISCONNECTED,
        model_status=ModelStatus.UNKNOWN,
        base_url="http://localhost:11434",
        model_name="llama3",
        error_message="Connection refused",
    )
    assert disconnected.is_connected is False
    assert disconnected.is_model_available is False


@patch("app.core.ollama_client.ollama.Client")
def test_get_status_connected_available(mock_client_cls: MagicMock) -> None:
    """Verify get_status reports CONNECTED and AVAILABLE when model is present."""
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance
    mock_instance.list.return_value = SimpleNamespace(
        models=[SimpleNamespace(model="llama3:latest"), SimpleNamespace(model="phi3")]
    )

    client = OllamaClient(default_model="llama3")
    status = client.get_status()

    assert status.server_status == ServerStatus.CONNECTED
    assert status.model_status == ModelStatus.AVAILABLE
    assert status.is_connected is True
    assert status.is_model_available is True
    assert "llama3:latest" in status.available_models


@patch("app.core.ollama_client.ollama.Client")
def test_get_status_connected_not_available(mock_client_cls: MagicMock) -> None:
    """Verify get_status reports CONNECTED and NOT_AVAILABLE when model is missing."""
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance
    mock_instance.list.return_value = SimpleNamespace(
        models=[SimpleNamespace(model="phi3:latest")]
    )

    client = OllamaClient(default_model="llama3")
    status = client.get_status()

    assert status.server_status == ServerStatus.CONNECTED
    assert status.model_status == ModelStatus.NOT_AVAILABLE
    assert status.is_connected is True
    assert status.is_model_available is False
    assert status.available_models == ["phi3:latest"]


@patch("app.core.ollama_client.ollama.Client")
def test_get_status_disconnected(mock_client_cls: MagicMock) -> None:
    """Verify get_status handles network disconnect gracefully without raising."""
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance
    mock_instance.list.side_effect = httpx.ConnectError("Connection refused")

    client = OllamaClient(default_model="llama3")
    status = client.get_status()

    assert status.server_status == ServerStatus.DISCONNECTED
    assert status.model_status == ModelStatus.UNKNOWN
    assert status.is_connected is False
    assert status.is_model_available is False
    assert status.available_models == []
    assert status.error_message is not None
