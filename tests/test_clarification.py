"""Unit tests for clarification intelligence and avoiding unnecessary questions."""

import pytest
from app.agent.intelligence_models import ActionType
from app.agent.intent import IntentAnalyzer


@pytest.fixture
def analyzer() -> IntentAnalyzer:
    return IntentAnalyzer()


def test_ambiguous_request_triggers_clarification(analyzer: IntentAnalyzer) -> None:
    # Highly ambiguous requests with missing targets
    ambig_prompts = [
        "Fix this",
        "Delete the report",
        "Open the application",
    ]
    for prompt in ambig_prompts:
        intent = analyzer.analyze(prompt)
        assert intent.action_type == ActionType.CLARIFICATION
        assert intent.clarification_prompt is not None
        assert intent.ambiguity_score > 0.5


def test_unambiguous_request_executes_directly_without_clarification(analyzer: IntentAnalyzer) -> None:
    # Unambiguous requests should not ask unnecessary questions
    direct_prompts = [
        "What is my RAM usage?",
        "What is 25 * 4?",
        "Explain recursion.",
        "Remember that my favorite editor is VSCode.",
    ]
    for prompt in direct_prompts:
        intent = analyzer.analyze(prompt)
        assert intent.action_type in {ActionType.TOOL, ActionType.ANSWER}
        assert intent.action_type != ActionType.CLARIFICATION
