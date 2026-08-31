"""Unit tests for context-length routing escalation and tool schema filtering."""

from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.selector import RequestCategory


def test_context_escalates_to_heavy_model_when_large() -> None:
    registry = ModelRegistry()
    mock_checker = MagicMock(spec=ModelAvailabilityChecker)
    mock_checker.list_installed_models.return_value = ["qwen2.5:0.5b", "qwen3:8b", "qwen3:30b"]
    mock_checker._model_matches.side_effect = lambda target, models: any(target in m for m in models)

    settings = Settings(max_context_bytes_for_standard=8000)
    router = ModelRouter(registry=registry, availability_checker=mock_checker, settings=settings)

    # Even a simple chat request with huge context (>8000 bytes) should route to HEAVY
    decision = router.route_request("Hello", context_bytes=12000)
    assert decision.role == ModelRole.HEAVY
    assert decision.selected_model == "qwen3:30b"


def test_tool_filtering_reduces_schema_set_for_simple_chat() -> None:
    registry = ModelRegistry()
    mock_checker = MagicMock(spec=ModelAvailabilityChecker)
    router = ModelRouter(registry=registry, availability_checker=mock_checker)

    all_schemas = [
        {"function": {"name": "get_current_time"}},
        {"function": {"name": "calculate"}},
        {"function": {"name": "delete_directory"}},
        {"function": {"name": "compile_c_program"}},
    ]

    filtered = router.filter_tools_for_request(RequestCategory.SIMPLE_CHAT, all_schemas)
    filtered_names = [s["function"]["name"] for s in filtered]
    assert "get_current_time" in filtered_names
    assert "calculate" in filtered_names
    assert "delete_directory" not in filtered_names
    assert "compile_c_program" not in filtered_names
