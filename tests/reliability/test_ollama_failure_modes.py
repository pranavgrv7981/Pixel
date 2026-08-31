"""Reliability tests for Ollama failure modes, timeouts, and degradation."""

import pytest
from unittest.mock import patch
from app.core.exceptions import ModelAPIError, OllamaConnectionError
from app.core.ollama_client import OllamaClient, ServerStatus
from app.core.config import Settings


def test_ollama_connection_failure_handling() -> None:
    settings = Settings(ollama_base_url="http://127.0.0.1:9999")  # Unreachable port
    client = OllamaClient(settings=settings)

    status = client.get_status()
    assert status.server_status == ServerStatus.DISCONNECTED


def test_ollama_api_error_translation() -> None:
    settings = Settings()
    client = OllamaClient(settings=settings)

    with patch.object(client._client, "chat", side_effect=Exception("Connection refused")):
        with pytest.raises(ModelAPIError):
            client.chat([{"role": "user", "content": "hi"}])
