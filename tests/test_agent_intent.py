"""Unit tests for IntentAnalyzer request interpretation and action routing."""

import pytest
from app.agent.intelligence_models import ActionType
from app.agent.intent import IntentAnalyzer


@pytest.fixture
def analyzer() -> IntentAnalyzer:
    return IntentAnalyzer()


def test_intent_greetings(analyzer: IntentAnalyzer) -> None:
    for greeting in ["hi", "hello", "good morning", "thanks", "hey there"]:
        intent = analyzer.analyze(greeting)
        assert intent.action_type == ActionType.ANSWER
        assert intent.category == "simple_chat"
        assert intent.requires_tools is False


def test_intent_explanatory_queries(analyzer: IntentAnalyzer) -> None:
    queries = [
        "Explain recursion.",
        "What is a pointer in C?",
        "How does garbage collection work in Python?",
        "Why is async I/O faster for network requests?",
    ]
    for q in queries:
        intent = analyzer.analyze(q)
        assert intent.action_type == ActionType.ANSWER
        assert intent.requires_tools is False


def test_intent_direct_tool_queries(analyzer: IntentAnalyzer) -> None:
    # Calculations
    i_calc = analyzer.analyze("What is 25 * 4?")
    assert i_calc.action_type == ActionType.TOOL
    assert "demo" in i_calc.suggested_tool_groups
    assert i_calc.requires_tools is True

    # System Metrics
    i_sys = analyzer.analyze("What is my current RAM usage?")
    assert i_sys.action_type == ActionType.TOOL
    assert "system" in i_sys.suggested_tool_groups
    assert i_sys.requires_tools is True

    # Applications
    i_app = analyzer.analyze("Open Notepad.")
    assert i_app.action_type == ActionType.TOOL
    assert "system" in i_app.suggested_tool_groups


def test_intent_planning_queries(analyzer: IntentAnalyzer) -> None:
    plans = [
        "Prepare my project for submission.",
        "Create a plan to inspect the repository, compile it, and run tests.",
        "Plan and execute building the project step by step.",
    ]
    for p in plans:
        intent = analyzer.analyze(p)
        assert intent.action_type == ActionType.PLAN
        assert intent.requires_planning is True


def test_intent_ambiguity_and_clarification(analyzer: IntentAnalyzer) -> None:
    ambiguous = [
        "Fix this",
        "Delete the report",
        "Open the application",
    ]
    for a in ambiguous:
        intent = analyzer.analyze(a)
        assert intent.action_type == ActionType.CLARIFICATION
        assert intent.clarification_prompt is not None
        assert len(intent.clarification_prompt) > 10


def test_intent_memory_and_knowledge(analyzer: IntentAnalyzer) -> None:
    i_mem = analyzer.analyze("Remember that my favorite language is Rust.")
    assert i_mem.action_type == ActionType.TOOL
    assert i_mem.requires_memory is True

    i_rag = analyzer.analyze("What is the codename of the project in my documents?")
    assert i_rag.action_type == ActionType.TOOL
    assert i_rag.requires_knowledge is True
