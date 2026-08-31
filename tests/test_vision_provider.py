"""Unit tests for OllamaVisionProvider multimodal payload dispatch."""

from unittest.mock import MagicMock
import pytest
from app.core.exceptions import ModelNotFoundError
from app.core.ollama_client import ModelResponse, OllamaClient
from app.vision.models import ImageFormat, ImageInput, ImageSource
from app.vision.providers import OllamaVisionProvider


def test_ollama_vision_provider_successful_analysis():
    """Verify OllamaVisionProvider constructs multimodal messages and returns structured VisionResult."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = ModelResponse("The image depicts an architecture flowchart with three nodes: A, B, and C.")

    provider = OllamaVisionProvider(client=mock_client)

    img = ImageInput(
        source=ImageSource.FILE,
        filename="diagram.png",
        width=400,
        height=300,
        size_bytes=50000,
        sha256_hash="dummyhash",
        base64_data="iVBORw0KGgoAAAANSUhEUg==",
    )

    result = provider.analyze(
        image_inputs=[img],
        prompt="Explain this diagram",
        model_name="llava:latest",
    )

    assert "flowchart" in result.text
    assert result.model == "llava:latest"
    assert result.processing_time_seconds >= 0.0
    assert result.metadata["image_count"] == 1

    # Verify mock client received messages with images array
    mock_client.chat.assert_called_once()
    called_args = mock_client.chat.call_args
    messages_payload = called_args[0][0]
    assert len(messages_payload) == 1
    assert messages_payload[0]["role"] == "user"
    assert messages_payload[0]["content"] == "Explain this diagram"
    assert messages_payload[0]["images"] == ["iVBORw0KGgoAAAANSUhEUg=="]
    assert called_args[1]["model"] == "llava:latest"


def test_ollama_vision_provider_empty_images_rejected():
    """Verify analyze raises ValueError when image_inputs list is empty."""
    provider = OllamaVisionProvider()
    with pytest.raises(ValueError) as exc:
        provider.analyze([], "test prompt", "llava:latest")
    assert "At least one ImageInput is required" in str(exc.value)


def test_ollama_vision_provider_missing_model_rejected():
    """Verify analyze raises ModelNotFoundError when model_name is empty."""
    provider = OllamaVisionProvider()
    img = ImageInput(source=ImageSource.FILE, base64_data="testb64")
    with pytest.raises(ModelNotFoundError):
        provider.analyze([img], "prompt", "")
