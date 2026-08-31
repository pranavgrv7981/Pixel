"""Unit tests for ModelRouter graceful fallback when preferred model is not installed."""

from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.core.exceptions import ModelNotFoundError
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter


def test_fallback_when_fast_model_missing() -> None:
    registry = ModelRegistry()
    mock_checker = MagicMock(spec=ModelAvailabilityChecker)
    # Only qwen3:30b is installed (exactly like the user's current environment)
    mock_checker.list_installed_models.return_value = ["qwen3:30b"]
    mock_checker._model_matches.side_effect = lambda target, models: target in models

    router = ModelRouter(registry=registry, availability_checker=mock_checker, settings=Settings())

    # User sends simple greeting that would prefer FAST (qwen2.5:0.5b)
    decision = router.route_request("Hello assistant!")
    assert decision.selected_model == "qwen3:30b"
    assert decision.is_fallback is True
    assert "Fallback to 'qwen3:30b'" in decision.reason


def test_fallback_disabled_raises_error() -> None:
    registry = ModelRegistry()
    mock_checker = MagicMock(spec=ModelAvailabilityChecker)
    mock_checker.list_installed_models.return_value = ["qwen3:30b"]
    mock_checker._model_matches.return_value = False

    settings = Settings(model_fallback_enabled=False)
    router = ModelRouter(registry=registry, availability_checker=mock_checker, settings=settings)

    with pytest.raises(ModelNotFoundError):
        router.route_request("Hello", explicit_mode="qwen2.5:0.5b")
