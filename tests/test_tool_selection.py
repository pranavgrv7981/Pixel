"""Unit tests for CapabilityToolSelector."""

import pytest
from app.agent.intelligence_models import ActionType, RequestIntent
from app.agent.tool_selector import CapabilityToolSelector


@pytest.fixture
def sample_schemas() -> list[dict]:
    return [
        {"name": "calculate", "description": "Safe math evaluator"},
        {"name": "get_memory_usage", "description": "Read host RAM usage"},
        {"name": "read_text_file", "description": "Read text file contents"},
        {"name": "compile_c_program", "description": "Compile C source code"},
        {"name": "browser_open", "description": "Open URL in headless browser"},
        {"name": "remember_memory", "description": "Store persistent memory"},
    ]


def test_tool_selector_bypasses_for_direct_answers(sample_schemas: list[dict]) -> None:
    selector = CapabilityToolSelector()
    intent = RequestIntent(
        raw_prompt="Explain recursion",
        normalized_goal="Explain concept",
        action_type=ActionType.ANSWER,
        requires_tools=False,
    )
    schemas, decision = selector.select_tools(intent, sample_schemas)
    assert schemas is None
    assert decision.selected_tools == []
    assert len(decision.bypassed_tools) == len(sample_schemas)


def test_tool_selector_filters_irrelevant_tools(sample_schemas: list[dict]) -> None:
    selector = CapabilityToolSelector()
    intent = RequestIntent(
        raw_prompt="What is my RAM usage?",
        normalized_goal="Query RAM metrics",
        action_type=ActionType.TOOL,
        requires_tools=True,
        suggested_tool_groups=["system"],
    )
    schemas, decision = selector.select_tools(intent, sample_schemas)
    assert schemas is not None
    assert len(schemas) == 1
    assert schemas[0]["name"] == "get_memory_usage"
    assert "browser_open" in decision.bypassed_tools
    assert "compile_c_program" in decision.bypassed_tools


def test_argument_plausibility_validation() -> None:
    selector = CapabilityToolSelector()

    # 1. Missing path
    valid1, reason1 = selector.validate_argument_plausibility("read_text_file", {})
    assert valid1 is False
    assert "Missing required 'path'" in reason1

    # 2. Ambiguous target path
    valid2, reason2 = selector.validate_argument_plausibility("delete_file", {"path": "this"})
    assert valid2 is False
    assert "Ambiguous target path" in reason2

    # 3. Valid file path
    valid3, reason3 = selector.validate_argument_plausibility("read_text_file", {"path": "E:/AI AGENT/data/test.txt"})
    assert valid3 is True

    # 4. Calculation checks
    valid4, _ = selector.validate_argument_plausibility("calculate", {"expression": ""})
    assert valid4 is False
