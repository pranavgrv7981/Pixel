"""Unit tests for ContextManager end-to-end assembly, diagnostics, and budgeting."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from app.core.config import Settings
from app.context.database import ContextDatabase
from app.context.manager import ContextManager
from app.context.models import ContextSource, ResponseStyle, UserProfile


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    mgr = MagicMock()
    rec = MagicMock()
    rec.category.value = "preference"
    rec.key = "favorite_editor"
    rec.value = "VSCode"
    rec.importance = 5
    mgr.get_relevant_memories.return_value = [rec]
    return mgr


@pytest.fixture
def mock_knowledge_manager() -> MagicMock:
    mgr = MagicMock()
    retriever = MagicMock()
    sc = MagicMock()
    sc.score = 0.88
    sc.chunk.document_id = "doc-1"
    sc.chunk.chunk_id = "chunk-1"
    sc.chunk.text = "FastAPI is a modern, fast web framework for building APIs with Python."
    retriever.search.return_value = [sc]
    mgr.retriever = retriever
    return mgr


@pytest.fixture
def context_manager(tmp_path: Path, mock_memory_manager: MagicMock, mock_knowledge_manager: MagicMock) -> ContextManager:
    db = ContextDatabase(db_path=tmp_path / "test_mgr.db")
    db.initialize()
    settings = Settings(
        max_context_tokens=8192,
        auto_system_context_enabled=True,
    )
    return ContextManager(
        db=db,
        memory_manager=mock_memory_manager,
        knowledge_manager=mock_knowledge_manager,
        settings=settings,
    )


def test_build_context_simple_chat(context_manager: ContextManager) -> None:
    # 1. Simple greeting
    payload, diag = context_manager.build_context(
        prompt="hi",
        conversation_id="conv-1",
        messages=[],
        system_prompt="You are a helpful assistant.",
    )
    assert len(payload) >= 2  # System message + User message
    assert payload[-1]["role"] == "user"
    assert payload[-1]["content"] == "hi"
    assert diag.included_items_count >= 1
    assert diag.latency_ms >= 0.0


def test_build_context_with_memories_and_knowledge(context_manager: ContextManager) -> None:
    # Query asking about editor and Python framework
    payload, diag = context_manager.build_context(
        prompt="What is my favorite editor and what is FastAPI?",
        conversation_id="conv-2",
        messages=[{"role": "user", "content": "hello"}, {"role": "assistant", "content": "Hi there!"}],
        system_prompt="You are a helpful assistant.",
    )
    system_content = payload[0]["content"]
    assert "favorite_editor = VSCode" in system_content
    assert "FastAPI is a modern" in system_content
    assert diag.source_breakdown.get("memory", 0) >= 1
    assert diag.source_breakdown.get("knowledge", 0) >= 1


def test_build_context_system_metrics(context_manager: ContextManager) -> None:
    payload, diag = context_manager.build_context(
        prompt="What is my current RAM usage?",
        conversation_id="conv-3",
        messages=[],
        system_prompt="System assistant.",
    )
    system_content = payload[0]["content"]
    assert "SYSTEM STATE METRICS:" in system_content
    assert "Memory:" in system_content
    assert diag.source_breakdown.get("system", 0) >= 1


def test_build_context_graceful_degradation(context_manager: ContextManager) -> None:
    # Corrupt collector to simulate internal error
    context_manager.collector = None  # type: ignore
    payload, diag = context_manager.build_context(
        prompt="hello after failure",
        conversation_id="conv-4",
        messages=[{"role": "user", "content": "first message"}],
        system_prompt="Base prompt",
    )
    # Should fall back cleanly without throwing an unhandled exception
    assert len(payload) >= 2
    assert len(diag.warnings) >= 1
