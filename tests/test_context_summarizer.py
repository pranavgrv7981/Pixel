"""Unit tests for ConversationSummarizer history compaction."""

import pytest
from pathlib import Path
from app.core.config import Settings
from app.context.database import ContextDatabase
from app.context.summarizer import ConversationSummarizer


@pytest.fixture
def summarizer(tmp_path: Path) -> ConversationSummarizer:
    db = ContextDatabase(db_path=tmp_path / "test_sum.db")
    db.initialize()
    settings = Settings(summarization_threshold_messages=6)
    return ConversationSummarizer(db=db, settings=settings)


def test_should_summarize(summarizer: ConversationSummarizer) -> None:
    assert summarizer.should_summarize(4) is False
    assert summarizer.should_summarize(6) is True
    assert summarizer.should_summarize(15) is True


def test_extract_key_points(summarizer: ConversationSummarizer) -> None:
    messages = [
        {"role": "user", "content": "I prefer using dark mode always."},
        {"role": "assistant", "content": "Understood, dark mode is active."},
        {"role": "user", "content": "How do I configure logging in Python?"},
        {"role": "assistant", "content": "Use logging.basicConfig()."},
    ]
    topics, decisions = summarizer.extract_key_points(messages)
    assert len(decisions) >= 1
    assert "dark mode" in decisions[0].lower()
    assert len(topics) >= 1
    assert "logging in python" in topics[0].lower()


def test_generate_summary_persistence(summarizer: ConversationSummarizer) -> None:
    messages = [
        {"role": "user", "content": "I want to build a local AI assistant with PySide6."},
        {"role": "assistant", "content": "Great, let's start by structuring the modules."},
        {"role": "user", "content": "We decided to use SQLite for memory persistence."},
    ]
    rec = summarizer.generate_summary("conv-test", messages)
    assert rec.conversation_id == "conv-test"
    assert rec.messages_summarized_count == 3
    assert "local ai assistant" in rec.summary.lower()

    # Retrieve cached from DB
    retrieved = summarizer.get_summary_for_conversation("conv-test")
    assert retrieved is not None
    assert retrieved.summary == rec.summary
