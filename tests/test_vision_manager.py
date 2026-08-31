"""Unit tests for VisionManager lifecycle, status detection, caching, and model routing."""

from unittest.mock import MagicMock
import pytest
from app.core.config import Settings
from app.core.exceptions import ModelNotFoundError, ToolValidationError
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelCapabilities, ModelProfile, ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.vision.manager import VisionManager
from app.vision.models import ImageFormat, ImageInput, ImageSource, VisionResult
from app.vision.providers import VisionProvider


def _build_test_manager(installed_models: list[str], vision_return_text: str = "Test analysis") -> VisionManager:
    """Helper creating a VisionManager with mocked model availability and vision provider."""
    settings = Settings()
    reg = ModelRegistry(settings=settings)
    avail = MagicMock(spec=ModelAvailabilityChecker)
    avail.list_installed_models.return_value = installed_models
    avail._model_matches.side_effect = lambda target, installed: any(target.lower() in inst.lower() for inst in installed)

    router = ModelRouter(registry=reg, availability_checker=avail, settings=settings)

    mock_provider = MagicMock(spec=VisionProvider)
    mock_provider.analyze.return_value = VisionResult(
        text=vision_return_text,
        model=installed_models[0] if installed_models else "none",
        processing_time_seconds=0.5,
    )

    return VisionManager(provider=mock_provider, router=router, settings=settings)


def test_vision_manager_status_when_no_vision_model_installed():
    """Verify VisionManager reports unavailable when only text models are installed."""
    manager = _build_test_manager(installed_models=["qwen3:30b"])
    status = manager.get_status()

    assert status.is_available is False
    assert status.active_model is None
    assert status.installed_vision_models == []
    assert "No vision-capable" in status.error_message


def test_vision_manager_status_when_vision_model_installed():
    """Verify VisionManager detects installed vision models."""
    manager = _build_test_manager(installed_models=["qwen3:30b", "llava:latest"])
    status = manager.get_status()

    assert status.is_available is True
    assert status.active_model == "llava:latest"
    assert "llava:latest" in status.installed_vision_models
    assert status.error_message is None


def test_vision_manager_analyze_images_caching():
    """Verify VisionManager caches repeated queries on the same image and prompt."""
    manager = _build_test_manager(installed_models=["llava:latest"], vision_return_text="First execution")

    img = ImageInput(
        source=ImageSource.FILE,
        filename="diagram.png",
        sha256_hash="uniquehash123",
        base64_data="abc",
    )

    res1 = manager.analyze_images([img], prompt="What is this?")
    assert res1.text == "First execution"
    assert manager.provider.analyze.call_count == 1

    # Second call should be served from memory cache without invoking provider
    res2 = manager.analyze_images([img], prompt="What is this?")
    assert res2.text == "First execution"
    assert manager.provider.analyze.call_count == 1  # unchanged


def test_vision_manager_reject_excessive_images():
    """Verify VisionManager rejects requests exceeding max_images_per_request limit."""
    manager = _build_test_manager(installed_models=["llava:latest"])
    img1 = ImageInput(source=ImageSource.FILE, base64_data="a")
    img2 = ImageInput(source=ImageSource.FILE, base64_data="b")
    img3 = ImageInput(source=ImageSource.FILE, base64_data="c")

    with pytest.raises(ToolValidationError) as exc:
        manager.analyze_images([img1, img2, img3])
    assert "exceeds maximum allowed per request" in str(exc.value)


def test_vision_manager_error_when_no_vision_model():
    """Verify analyze_images raises ModelNotFoundError when no vision model is installed."""
    manager = _build_test_manager(installed_models=["qwen3:30b"])
    img = ImageInput(source=ImageSource.FILE, base64_data="a")

    with pytest.raises(ModelNotFoundError) as exc:
        manager.analyze_images([img], "Describe this")
    assert "No vision-capable local model" in str(exc.value)
