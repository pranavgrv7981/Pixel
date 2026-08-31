"""Unit tests for memory quality and conflict resolution policy."""

import pytest
from app.agent.intelligence_models import ActionType
from app.agent.intent import IntentAnalyzer
from app.context.models import ContextItem, ContextSource, TrustLevel
from app.context.ranker import ContextRanker


def test_memory_intent_gating() -> None:
    analyzer = IntentAnalyzer()

    # Explicit memory statements trigger memory intent
    intent_mem = analyzer.analyze("Remember that my main project is Atlas.")
    assert intent_mem.requires_memory is True

    # Casual chat statements do NOT automatically trigger memory intent
    intent_casual = analyzer.analyze("The sky looks beautiful today.")
    assert intent_casual.requires_memory is False


def test_current_instruction_overrides_memory() -> None:
    ranker = ContextRanker()

    # User currently asks for detailed explanation
    current_prompt = "Give me a detailed, long explanation of pointers."

    # Persistent memory says user prefers concise responses
    mem_item = ContextItem(
        source=ContextSource.MEMORY,
        content="User prefers concise responses.",
        trust_level=TrustLevel.MEMORY,
        priority=4,
        is_mandatory=False,
    )

    # Current prompt has higher trust level (USER=90 vs MEMORY=70) and mandatory priority
    prompt_item = ContextItem(
        source=ContextSource.CURRENT_MESSAGE,
        content=current_prompt,
        trust_level=TrustLevel.USER,
        priority=1,
        is_mandatory=True,
    )

    ranked = ranker.rank_candidates(current_prompt, [mem_item, prompt_item])
    # Current prompt takes strict precedence
    assert ranked[0].id == prompt_item.id
    assert ranked[0].trust_level > ranked[1].trust_level
