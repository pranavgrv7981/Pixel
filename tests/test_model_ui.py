"""Unit tests for UI model routing display, selection, and status indicators."""

from unittest.mock import MagicMock
import pytest

from app.models.availability import ModelAvailabilityChecker, ModelAvailabilityStatus
from app.models.profiles import ModelRole
from app.models.registry import ModelRegistry


def test_ui_model_status_formatting() -> None:
    registry = ModelRegistry()
    mock_checker = MagicMock(spec=ModelAvailabilityChecker)
    mock_checker.list_installed_models.return_value = ["qwen3:30b"]
    mock_checker.get_loaded_models.return_value = []
    mock_checker._model_matches.side_effect = lambda target, models: target in models

    checker = ModelAvailabilityChecker(client=MagicMock())
    checker.list_installed_models = mock_checker.list_installed_models
    checker.get_loaded_models = mock_checker.get_loaded_models
    checker._model_matches = mock_checker._model_matches

    statuses = checker.get_all_statuses(registry)
    status_map = {s.name: s.installed for s in statuses}

    assert status_map["qwen3:30b"] is True
    assert status_map.get("qwen2.5:0.5b") is False
    assert status_map.get("qwen3:8b") is False
