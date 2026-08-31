"""Tests for MemoryManager coordination, validation, and bounded relevance retrieval."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.core.exceptions import ToolValidationError
from app.memory.manager import MemoryManager
from app.memory.models import MemoryCategory, MemorySource


@pytest.fixture
def manager(tmp_path: Path) -> MemoryManager:
    db_file = tmp_path / "test_mgr.db"
    settings = Settings(
        memory_database_path=str(db_file),
        max_recalled_memories=2,
    )
    mgr = MemoryManager(settings=settings)
    mgr.initialize()
    return mgr


def test_remember_and_category_validation(manager: MemoryManager) -> None:
    # Valid remember
    rec = manager.remember("PROJECT", "main_project", "Atlas", importance=8)
    assert rec.category == MemoryCategory.PROJECT
    assert rec.key == "main_project"
    assert rec.value == "Atlas"

    # Invalid category raises ToolValidationError
    with pytest.raises(ToolValidationError) as exc_info:
        manager.remember("INVALID_CAT", "foo", "bar")
    assert "Unknown memory category" in str(exc_info.value)

    # Empty key raises ToolValidationError
    with pytest.raises(ToolValidationError) as exc_info:
        manager.remember("PREFERENCE", "   ", "dark")
    assert "cannot be empty" in str(exc_info.value)


def test_recall_and_limit(manager: MemoryManager) -> None:
    manager.remember("PREFERENCE", "theme", "dark", importance=5)
    manager.remember("PREFERENCE", "font", "JetBrains Mono", importance=6)
    manager.remember("PROJECT", "main_project", "Atlas", importance=9)

    # Recall by category with max limit=2 enforced
    results = manager.recall(category="PREFERENCE")
    assert len(results) == 2

    # Recall by specific query
    atlas = manager.recall(query="Atlas")
    assert len(atlas) == 1
    assert atlas[0].key == "main_project"


def test_get_relevant_memories_keyword_extraction(manager: MemoryManager) -> None:
    manager.remember("PROJECT", "main_project", "Atlas", importance=9)
    manager.remember("PREFERENCE", "editor", "VS Code", importance=7)
    manager.remember("PERSONAL_FACT", "hometown", "Seattle", importance=4)

    # Query with stop words: "What is my main project?" -> matches "project"
    relevant = manager.get_relevant_memories("What is my main project?")
    assert len(relevant) == 1
    assert relevant[0].key == "main_project"

    # Query with editor keyword: "Tell me about my editor" -> matches "editor"
    editor_rel = manager.get_relevant_memories("Tell me about my editor")
    assert len(editor_rel) == 1
    assert editor_rel[0].key == "editor"

    # Unrelated query -> returns empty list (does not inject unrelated memories)
    unrelated = manager.get_relevant_memories("Calculate the square root of 144")
    assert unrelated == []


def test_format_memories_for_prompt(manager: MemoryManager) -> None:
    manager.remember("PROJECT", "main_project", "Atlas", importance=9)
    mems = manager.recall(query="Atlas")
    prompt_block = manager.format_memories_for_prompt(mems)

    assert "[Persistent User Context & Memories]" in prompt_block
    assert "[PROJECT] main_project: Atlas" in prompt_block

    # Empty memories returns empty string
    assert manager.format_memories_for_prompt([]) == ""
