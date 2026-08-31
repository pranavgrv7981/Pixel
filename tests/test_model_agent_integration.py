"""Unit tests verifying Agent integration with ModelRouter and metrics tracking."""

from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.models.availability import ModelAvailabilityChecker
from app.models.metrics import ModelMetricsTracker
from app.models.profiles import ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter, RoutingDecision
from app.models.selector import RequestCategory
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry


def test_agent_routes_through_model_router() -> None:
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = ModelResponse(content="Model reply")
    mock_client.default_model = "qwen3:30b"

    registry = ToolRegistry()
    perm_mgr = PermissionManager(settings=Settings())
    metrics = ModelMetricsTracker()

    mock_router = MagicMock(spec=ModelRouter)
    mock_router.route_request.return_value = RoutingDecision(
        selected_model="qwen3:8b",
        role=ModelRole.STANDARD,
        category=RequestCategory.CODE_TASK,
        reason="Test route",
    )
    mock_router.filter_tools_for_request.side_effect = lambda cat, schemas: schemas

    agent = Agent(
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
        router=mock_router,
        metrics_tracker=metrics,
    )

    response = agent.run("Compile this C code")
    assert response == "Model reply"
    assert agent.last_routing_decision is not None
    assert agent.last_routing_decision.selected_model == "qwen3:8b"

    # Ensure model was passed to client.chat
    mock_client.chat.assert_called_once()
    _, kwargs = mock_client.chat.call_args
    assert kwargs["model"] == "qwen3:8b"

    # Ensure metrics were tracked
    summary = metrics.get_summary()
    assert summary["total_requests"] == 1
    assert summary["models_used"]["qwen3:8b"] == 1
