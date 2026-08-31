"""Unit tests for ModelRouter dynamic auto routing and explicit overrides."""

from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.selector import RequestCategory


@pytest.fixture
def router_setup() -> ModelRouter:
    registry = ModelRegistry()
    mock_checker = MagicMock(spec=ModelAvailabilityChecker)
    # Simulate all three models installed
    mock_checker.list_installed_models.return_value = ["qwen2.5:0.5b", "qwen3:8b", "qwen3:30b"]
    mock_checker._model_matches.side_effect = lambda target, models: any(target in m for m in models)

    router = ModelRouter(registry=registry, availability_checker=mock_checker, settings=Settings())
    return router


def test_router_selects_fast_for_greeting(router_setup: ModelRouter) -> None:
    decision = router_setup.route_request("Hello assistant! How are you today?")
    assert decision.role == ModelRole.FAST
    assert decision.category == RequestCategory.SIMPLE_CHAT
    assert decision.selected_model == "qwen2.5:0.5b"


def test_router_selects_standard_for_code_and_rag(router_setup: ModelRouter) -> None:
    decision_code = router_setup.route_request("Please compile my main.c program and run pytest")
    assert decision_code.role == ModelRole.STANDARD
    assert decision_code.selected_model == "qwen3:8b"

    decision_rag = router_setup.route_request("Search my notes for the project deadline in my documents")
    assert decision_rag.role == ModelRole.STANDARD


def test_router_selects_heavy_for_planning(router_setup: ModelRouter) -> None:
    decision = router_setup.route_request("Plan and execute a multi-step test of our C application", is_planning=True)
    assert decision.role == ModelRole.HEAVY
    assert decision.selected_model == "qwen3:30b"


def test_router_explicit_override(router_setup: ModelRouter) -> None:
    decision = router_setup.route_request("Hello", explicit_mode="qwen3:30b")
    assert decision.selected_model == "qwen3:30b"
    assert "Explicit model override" in decision.reason
