"""Unit tests for PlanValidator structural, tool, and circular dependency checks."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.planning.models import Plan, PlanStep
from app.planning.validator import PlanValidator
from app.tools.demo import GetCurrentTimeTool, SafeCalculateTool
from app.tools.filesystem import ReadTextFileTool
from app.tools.path_guard import PathGuard
from app.tools.registry import ToolRegistry


@pytest.fixture
def test_registry(tmp_path: Path) -> ToolRegistry:
    reg = ToolRegistry()
    guard = PathGuard(allowed_roots=[tmp_path])
    reg.register(GetCurrentTimeTool())
    reg.register(SafeCalculateTool())
    reg.register(ReadTextFileTool(path_guard=guard))
    return reg


def test_validator_rejects_empty_plan(test_registry: ToolRegistry) -> None:
    validator = PlanValidator(registry=test_registry)
    plan = Plan(goal="Do nothing", steps=[])
    is_valid, errors = validator.validate_plan(plan)
    assert is_valid is False
    assert any("at least one step" in e for e in errors)


def test_validator_rejects_unknown_tool(test_registry: ToolRegistry) -> None:
    validator = PlanValidator(registry=test_registry)
    step = PlanStep(order=1, description="Bad tool", tool_name="nonexistent_tool_xyz")
    plan = Plan(goal="Bad task", steps=[step])
    is_valid, errors = validator.validate_plan(plan)
    assert is_valid is False
    assert any("unknown tool" in e for e in errors)


def test_validator_detects_circular_dependencies(test_registry: ToolRegistry) -> None:
    validator = PlanValidator(registry=test_registry)
    s1 = PlanStep(order=1, description="Step 1", tool_name="get_current_time", dependencies=["2"])
    s2 = PlanStep(order=2, description="Step 2", tool_name="calculate", parameters={"expression": "1+1"}, dependencies=["1"])
    plan = Plan(goal="Circular task", steps=[s1, s2])

    is_valid, errors = validator.validate_plan(plan)
    assert is_valid is False
    assert any("circular or deadlock" in e for e in errors)


def test_validator_passes_valid_sequential_plan(test_registry: ToolRegistry) -> None:
    validator = PlanValidator(registry=test_registry)
    s1 = PlanStep(order=1, description="Get time", tool_name="get_current_time")
    s2 = PlanStep(order=2, description="Calculate", tool_name="calculate", parameters={"expression": "25 * 4"}, dependencies=["1"])
    plan = Plan(goal="Calculate task", steps=[s1, s2])

    is_valid, errors = validator.validate_plan(plan)
    assert is_valid is True
    assert len(errors) == 0
