"""Unit tests for Planner goal decomposition and dynamic re-planning."""

from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.planning.models import FailureType, Plan, PlanStep, StepStatus
from app.planning.planner import Planner
from app.planning.validator import PlanValidator
from app.tools.demo import GetCurrentTimeTool, SafeCalculateTool
from app.tools.registry import ToolRegistry


@pytest.fixture
def planner_setup() -> tuple[Planner, ToolRegistry]:
    reg = ToolRegistry()
    reg.register(GetCurrentTimeTool())
    reg.register(SafeCalculateTool())

    validator = PlanValidator(registry=reg)
    mock_client = MagicMock(spec=OllamaClient)
    planner = Planner(client=mock_client, registry=reg, validator=validator)
    return planner, reg


def test_planner_generates_template_plan_for_known_goals(planner_setup: tuple[Planner, ToolRegistry]) -> None:
    planner, _ = planner_setup
    plan = planner.create_plan("Prepare my C project for submission")
    assert plan is not None
    assert len(plan.steps) >= 1
    assert "Prepare" in plan.goal


def test_planner_parses_llm_json_response(planner_setup: tuple[Planner, ToolRegistry]) -> None:
    planner, _ = planner_setup
    mock_json = """
    {
      "goal": "Calculate multiplication",
      "success_criteria": ["Result is 100"],
      "steps": [
        {
          "order": 1,
          "description": "Calculate 25 * 4",
          "tool_name": "calculate",
          "parameters": {"expression": "25 * 4"},
          "dependencies": []
        }
      ]
    }
    """
    planner.client.chat.return_value = mock_json

    plan = planner.create_plan("Custom math task")
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "calculate"
    assert plan.steps[0].parameters == {"expression": "25 * 4"}
