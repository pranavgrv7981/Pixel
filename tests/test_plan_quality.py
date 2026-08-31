"""Unit tests for Plan Quality and adaptive execution activation."""

import pytest
from app.agent.intelligence_models import ActionType
from app.agent.intent import IntentAnalyzer


def test_planning_intent_activation() -> None:
    analyzer = IntentAnalyzer()

    complex_workflow = "Prepare my project for submission."
    intent = analyzer.analyze(complex_workflow)
    assert intent.action_type == ActionType.PLAN
    assert intent.requires_planning is True


def test_simple_queries_do_not_trigger_planner() -> None:
    analyzer = IntentAnalyzer()

    # Simple math
    i1 = analyzer.analyze("What is 2 + 2?")
    assert i1.action_type != ActionType.PLAN
    assert i1.requires_planning is False

    # Simple system query
    i2 = analyzer.analyze("What is my RAM usage?")
    assert i2.action_type != ActionType.PLAN
    assert i2.requires_planning is False

    # Simple explanation
    i3 = analyzer.analyze("Explain recursion.")
    assert i3.action_type != ActionType.PLAN
    assert i3.requires_planning is False
