"""Unit tests for ModelRouter handling multimodal vision requests and fallbacks."""

from unittest.mock import MagicMock
import pytest
from app.core.config import Settings
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter, RoutingDecision


def test_text_only_request_routes_to_text_models():
    """Verify text-only requests do not route to vision role."""
    settings = Settings()
    reg = ModelRegistry(settings=settings)
    avail = MagicMock(spec=ModelAvailabilityChecker)
    avail.list_installed_models.return_value = ["qwen3:30b", "llava:latest"]
    avail._model_matches.side_effect = lambda target, installed: any(target.lower() in inst.lower() for inst in installed)

    router = ModelRouter(registry=reg, availability_checker=avail, settings=settings)

    decision = router.route_request("Hello, what is the capital of France?", has_images=False)
    assert decision.role in (ModelRole.FAST, ModelRole.STANDARD, ModelRole.HEAVY)
    assert decision.selected_model == "qwen3:30b"


def test_multimodal_request_routes_to_vision_model_when_installed():
    """Verify requests with has_images=True select the installed vision model."""
    settings = Settings()
    reg = ModelRegistry(settings=settings)
    avail = MagicMock(spec=ModelAvailabilityChecker)
    avail.list_installed_models.return_value = ["qwen3:30b", "llava:latest"]
    avail._model_matches.side_effect = lambda target, installed: any(target.lower() in inst.lower() for inst in installed)

    router = ModelRouter(registry=reg, availability_checker=avail, settings=settings)

    decision = router.route_request("What is in this image?", has_images=True)
    assert decision.role == ModelRole.VISION
    assert decision.selected_model == "llava:latest"
    assert "Vision model selected" in decision.reason


def test_multimodal_request_graceful_handling_when_no_vision_model():
    """Verify router returns empty selected model and diagnostic reason when no vision model is installed."""
    settings = Settings()
    reg = ModelRegistry(settings=settings)
    avail = MagicMock(spec=ModelAvailabilityChecker)
    avail.list_installed_models.return_value = ["qwen3:30b"]
    avail._model_matches.side_effect = lambda target, installed: any(target.lower() in inst.lower() for inst in installed)

    router = ModelRouter(registry=reg, availability_checker=avail, settings=settings)

    decision = router.route_request("Explain this diagram", has_images=True)
    assert decision.role == ModelRole.VISION
    assert decision.selected_model == ""
    assert "No vision-capable local model installed" in decision.reason
