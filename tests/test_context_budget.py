"""Unit tests for ContextBudgetCalculator model capacity and source limits."""

import pytest
from app.core.config import Settings
from app.context.budget import ContextBudgetCalculator
from app.context.models import ContextItem, ContextSource, TrustLevel


def test_calculate_budget_defaults_and_reserve() -> None:
    settings = Settings(
        max_context_tokens=12288,
        response_token_reserve=2048,
    )
    calc = ContextBudgetCalculator(settings=settings)

    budget = calc.calculate_budget(
        model_capacity=16384,
        system_prompt="You are a helpful assistant.",
        tool_schemas=[{"name": "calc", "description": "calculate"}],
    )
    assert budget.total_model_capacity == 16384
    assert budget.response_reserve_tokens == 2048
    assert budget.system_prompt_tokens > 0
    assert budget.tool_schemas_tokens > 0
    assert budget.available_input_tokens <= 12288


def test_pack_items_respects_limits_and_mandatory() -> None:
    settings = Settings(
        max_context_tokens=100,
        max_memory_context_tokens=30,
    )
    calc = ContextBudgetCalculator(settings=settings)
    budget = calc.calculate_budget(model_capacity=200)
    budget.available_input_tokens = 60

    # Mandatory prompt item (20 tokens)
    mandatory = ContextItem(
        source=ContextSource.CURRENT_MESSAGE,
        content="What is the weather today?",
        is_mandatory=True,
        estimated_tokens=20,
    )

    # Optional memory item 1 (25 tokens, fits under memory limit of 30)
    mem1 = ContextItem(
        source=ContextSource.MEMORY,
        content="User lives in San Francisco.",
        is_mandatory=False,
        estimated_tokens=25,
        priority=4,
        relevance_score=0.9,
    )

    # Optional memory item 2 (20 tokens, would exceed memory limit 25+20=45 > 30)
    mem2 = ContextItem(
        source=ContextSource.MEMORY,
        content="User previously visited Seattle.",
        is_mandatory=False,
        estimated_tokens=20,
        priority=5,
        relevance_score=0.8,
    )

    included, excluded = calc.pack_items([mandatory, mem1, mem2], budget)
    assert mandatory in included
    assert mem1 in included
    assert mem2 in excluded
    assert budget.used_tokens == 45
