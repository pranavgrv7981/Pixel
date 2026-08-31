"""Integration tests for end-to-end multimodal agent execution."""

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
from app.vision.models import ImageInput, ImageSource


def _create_test_agent(installed_models: list[str], mocked_response_text: str = "Vision analysis result"):
    """Helper building a complete Agent with mocked OllamaClient and availability."""
    settings = Settings()
    client = MagicMock(spec=OllamaClient)
    client.default_model = installed_models[0] if installed_models else "qwen3:30b"
    client.chat.return_value = ModelResponse(mocked_response_text)
    client.stream_chat.return_value = [mocked_response_text]

    conv = Conversation()
    tool_reg = ToolRegistry()
    perm_mgr = PermissionManager(settings=settings)

    model_reg = ModelRegistry(settings=settings)
    avail = MagicMock(spec=ModelAvailabilityChecker)
    avail.list_installed_models.return_value = installed_models
    avail._model_matches.side_effect = lambda target, installed: any(target.lower() in inst.lower() for inst in installed)

    router = ModelRouter(registry=model_reg, availability_checker=avail, settings=settings)

    agent = Agent(
        client=client,
        conversation=conv,
        registry=tool_reg,
        permission_manager=perm_mgr,
        router=router,
        settings=settings,
    )
    return agent, client


def test_agent_run_with_images_no_vision_model():
    """Verify Agent.run gracefully informs user when images are provided but no vision model is installed."""
    agent, client = _create_test_agent(installed_models=["qwen3:30b"])

    img = ImageInput(
        source=ImageSource.FILE,
        filename="diagram.png",
        base64_data="iVBORw0KGgoAAAANSUhEUg==",
    )

    resp = agent.run("What is in this diagram?", images=[img])
    assert "Vision analysis is unavailable" in resp
    assert "No vision-capable local model" in resp


def test_agent_run_with_images_vision_model_installed():
    """Verify Agent.run dispatches multimodal payloads when a vision model is installed."""
    agent, client = _create_test_agent(installed_models=["qwen3:30b", "llava:latest"], mocked_response_text="The diagram shows 3 nodes: A -> B -> C.")

    img = ImageInput(
        source=ImageSource.FILE,
        filename="diagram.png",
        base64_data="iVBORw0KGgoAAAANSUhEUg==",
    )

    resp = agent.run("What is in this diagram?", images=[img])
    assert "3 nodes: A -> B -> C" in resp

    # Check client.chat was called with images payload
    client.chat.assert_called_once()
    called_payload = client.chat.call_args[0][0]
    last_msg = called_payload[-1]
    assert "images" in last_msg
    assert last_msg["images"] == ["iVBORw0KGgoAAAANSUhEUg=="]


def test_agent_stream_run_with_images():
    """Verify Agent.stream_run yields chunks when images are provided."""
    agent, client = _create_test_agent(installed_models=["llava:latest"], mocked_response_text="Image analysis stream")

    img = ImageInput(
        source=ImageSource.FILE,
        filename="diagram.png",
        base64_data="iVBORw0KGgoAAAANSUhEUg==",
    )

    chunks = list(agent.stream_run("Explain this image", images=[img]))
    full_text = "".join(chunks)
    assert "Image analysis stream" in full_text
