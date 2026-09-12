"""Unit tests for FastChatProfile and Ollama thinking tag control."""

from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.models.profiles import FastChatProfile


def test_fast_chat_profile_defaults():
    """Verify default FastChatProfile values conform to specification."""
    profile = FastChatProfile()
    assert profile.model == "qwen3:4b"
    assert profile.think is False
    assert profile.num_ctx == 2048
    assert profile.num_predict == 384
    assert profile.temperature == 0.4
    assert profile.keep_alive == "30m"

    opts = profile.to_ollama_options()
    assert opts["num_ctx"] == 2048
    assert opts["num_predict"] == 384
    assert opts["temperature"] == 0.4


def test_ollama_stream_chat_thinking_tags_filtered():
    """Verify that <think>...</think> tags are stripped when think=False."""
    client = OllamaClient()

    # Simulate chunks emitted by reasoning model with think block
    mock_chunks = [
        {"message": {"content": "<think>Let me compute this internally</think>"}},
        {"message": {"content": "Hello!"}},
        {"message": {"content": " How can I help you today?"}},
    ]

    with patch.object(client._client, "chat", return_value=mock_chunks):
        received_tokens = list(client.stream_chat([{"role": "user", "content": "hi"}], think=False))
        combined = "".join(received_tokens)

        assert "<think>" not in combined
        assert "Let me compute" not in combined
        assert combined == "Hello! How can I help you today?"


def test_ollama_stream_chat_split_thinking_tags():
    """Verify thinking tags spanning multiple chunks are filtered cleanly."""
    client = OllamaClient()

    mock_chunks = [
        {"message": {"content": "<think>"}},
        {"message": {"content": "Deep reasoning chunk 1\n"}},
        {"message": {"content": "Deep reasoning chunk 2"}},
        {"message": {"content": "</think>Direct answer text"}},
    ]

    with patch.object(client._client, "chat", return_value=mock_chunks):
        received_tokens = list(client.stream_chat([{"role": "user", "content": "hi"}], think=False))
        combined = "".join(received_tokens)

        assert "<think>" not in combined
        assert "</think>" not in combined
        assert "Deep reasoning" not in combined
        assert combined == "Direct answer text"
