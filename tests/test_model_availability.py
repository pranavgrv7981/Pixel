"""Unit tests for ModelAvailabilityChecker presence verification."""

from unittest.mock import MagicMock
import pytest

from app.core.exceptions import OllamaConnectionError
from app.core.ollama_client import OllamaClient
from app.models.availability import ModelAvailabilityChecker
from app.models.registry import ModelRegistry


def test_availability_checker_installed_and_missing() -> None:
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.list_models.return_value = ["qwen3:30b:latest"]
    mock_client.base_url = "http://localhost:11434"

    checker = ModelAvailabilityChecker(client=mock_client)

    status_installed = checker.check_availability("qwen3:30b")
    assert status_installed.installed is True
    assert status_installed.available is True

    status_missing = checker.check_availability("qwen2.5:0.5b")
    assert status_missing.installed is False
    assert status_missing.available is False


def test_availability_checker_server_offline() -> None:
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.list_models.side_effect = OllamaConnectionError("Connection refused")
    mock_client.base_url = "http://localhost:11434"

    checker = ModelAvailabilityChecker(client=mock_client)
    assert checker.list_installed_models() == []
