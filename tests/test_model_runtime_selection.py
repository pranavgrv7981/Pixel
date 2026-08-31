"""Regression tests verifying model selection during conversational requests."""

from unittest.mock import MagicMock
from app.core.config import Settings
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter


def test_model_router_selects_installed_heavy_when_only_one_model():
    """Verify router selects installed qwen3:30b for chat queries when only heavy model is installed."""
    settings = Settings()
    reg = ModelRegistry(settings=settings)
    avail = MagicMock(spec=ModelAvailabilityChecker)
    avail.list_installed_models.return_value = ["qwen3:30b"]
    avail._model_matches.side_effect = lambda target, installed: any(target.lower() in inst.lower() for inst in installed)

    router = ModelRouter(registry=reg, availability_checker=avail, settings=settings)

    decision = router.route_request("hi")
    assert decision.selected_model == "qwen3:30b"
    assert decision.role in (ModelRole.FAST, ModelRole.STANDARD, ModelRole.HEAVY)
