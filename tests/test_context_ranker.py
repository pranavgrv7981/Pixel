"""Unit tests for ContextRanker token estimation and relevance scoring."""

import pytest
from app.context.models import ContextItem, ContextSource, ProjectContext, TrustLevel
from app.context.ranker import ContextRanker, estimate_tokens, extract_keywords


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0
    assert estimate_tokens("hi") >= 1
    # 100 character sentence -> approx 25 tokens
    text = "The quick brown fox jumps over the lazy dog and explores the wonders of the forest every morning."
    tokens = estimate_tokens(text)
    assert 20 <= tokens <= 35


def test_extract_keywords() -> None:
    text = "What is the CPU usage and RAM status on my Windows machine?"
    kw = extract_keywords(text)
    assert "cpu" in kw
    assert "usage" in kw
    assert "ram" in kw
    assert "status" in kw
    assert "windows" in kw
    assert "machine" in kw
    # Stop words omitted
    assert "is" not in kw
    assert "the" not in kw
    assert "and" not in kw
    assert "on" not in kw
    assert "my" not in kw


def test_is_system_query() -> None:
    ranker = ContextRanker()
    assert ranker.is_system_query("What is my current RAM usage?") is True
    assert ranker.is_system_query("Check CPU load and hardware specs") is True
    assert ranker.is_system_query("Explain recursion in Python") is False
    assert ranker.is_system_query("What is 25 * 4?") is False


def test_score_relevance_keyword_and_phrase_overlap() -> None:
    ranker = ContextRanker()

    item_relevant = ContextItem(
        source=ContextSource.MEMORY,
        content="User favorite programming language is Python and Rust.",
        category="preference",
    )
    score_rel = ranker.score_relevance("What is my favorite programming language?", item_relevant)
    assert score_rel >= 0.70

    item_irrelevant = ContextItem(
        source=ContextSource.MEMORY,
        content="Meeting with dentist scheduled at 4 PM.",
        category="task",
    )
    score_irrel = ranker.score_relevance("What is my favorite programming language?", item_irrelevant)
    assert score_irrel < score_rel


def test_rank_candidates_preserves_mandatory() -> None:
    ranker = ContextRanker()

    prompt_item = ContextItem(
        source=ContextSource.CURRENT_MESSAGE,
        content="hi",
        is_mandatory=True,
        priority=1,
    )
    optional_item = ContextItem(
        source=ContextSource.MEMORY,
        content="Unrelated memory fact.",
        is_mandatory=False,
        priority=5,
    )

    ranked = ranker.rank_candidates("hi", [optional_item, prompt_item])
    assert ranked[0].id == prompt_item.id
    assert ranked[0].is_mandatory is True
