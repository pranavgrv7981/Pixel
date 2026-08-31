"""Tests for ConversationRepository and MemoryRepository implementations."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.memory.database import MemoryDatabase
from app.memory.models import MemoryCategory, MemorySource
from app.memory.repository import ConversationRepository, MemoryRepository


@pytest.fixture
def repo_env(tmp_path: Path) -> tuple[ConversationRepository, MemoryRepository, Settings]:
    db_file = tmp_path / "test_repos.db"
    settings = Settings(
        memory_database_path=str(db_file),
        max_persisted_messages=5,
    )
    db = MemoryDatabase(db_path=db_file, settings=settings)
    db.initialize()
    conv_repo = ConversationRepository(db=db, settings=settings)
    mem_repo = MemoryRepository(db=db)
    return conv_repo, mem_repo, settings


def test_conversation_crud_and_messages(
    repo_env: tuple[ConversationRepository, MemoryRepository, Settings]
) -> None:
    conv_repo, _, _ = repo_env

    # 1. Create conversation
    conv = conv_repo.create_conversation(title="Project Atlas Discussion")
    assert conv.id is not None
    assert conv.title == "Project Atlas Discussion"

    # 2. Get conversation
    fetched = conv_repo.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.title == "Project Atlas Discussion"

    # 3. Append messages and check ordering
    m1 = conv_repo.append_message(conv.id, "user", "Hello world")
    m2 = conv_repo.append_message(conv.id, "assistant", "Hi there")
    assert m1.sequence_number == 1
    assert m2.sequence_number == 2

    msgs = conv_repo.get_messages(conv.id)
    assert len(msgs) == 2
    assert msgs[0].content == "Hello world"
    assert msgs[1].content == "Hi there"

    # 4. List conversations
    convs = conv_repo.list_conversations()
    assert len(convs) >= 1
    assert any(c.id == conv.id for c in convs)

    # 5. Delete conversation
    deleted = conv_repo.delete_conversation(conv.id)
    assert deleted is True
    assert conv_repo.get_conversation(conv.id) is None
    assert conv_repo.get_messages(conv.id) == []


def test_message_retention_limit_pruning(
    repo_env: tuple[ConversationRepository, MemoryRepository, Settings]
) -> None:
    conv_repo, _, settings = repo_env
    # Max messages configured to 5
    conv = conv_repo.create_conversation(title="Long Session")

    # Insert 8 messages
    for i in range(1, 9):
        conv_repo.append_message(conv.id, "user" if i % 2 == 1 else "assistant", f"Message {i}")

    msgs = conv_repo.get_messages(conv.id)
    assert len(msgs) == 5
    # Oldest 3 messages (1, 2, 3) must have been pruned; newest 5 (4, 5, 6, 7, 8) retained
    assert msgs[0].content == "Message 4"
    assert msgs[4].content == "Message 8"


def test_memory_upsert_and_deduplication(
    repo_env: tuple[ConversationRepository, MemoryRepository, Settings]
) -> None:
    _, mem_repo, _ = repo_env

    # 1. Insert memory
    rec1 = mem_repo.upsert_memory(
        category=MemoryCategory.PROJECT,
        key="main_project",
        value="Atlas",
        importance=8,
        source=MemorySource.USER,
    )
    assert rec1.key == "main_project"
    assert rec1.value == "Atlas"
    assert rec1.importance == 8

    # 2. Update same logical memory with new value
    rec2 = mem_repo.upsert_memory(
        category=MemoryCategory.PROJECT,
        key="main_project",
        value="Phoenix",
        importance=9,
        source=MemorySource.USER,
    )
    assert rec2.value == "Phoenix"
    assert rec2.importance == 9

    # 3. Verify deduplication: only 1 record exists
    all_mems = mem_repo.list_memories()
    project_mems = [m for m in all_mems if m.key == "main_project"]
    assert len(project_mems) == 1
    assert project_mems[0].value == "Phoenix"


def test_memory_search_and_retrieval(
    repo_env: tuple[ConversationRepository, MemoryRepository, Settings]
) -> None:
    _, mem_repo, _ = repo_env

    mem_repo.upsert_memory(MemoryCategory.PREFERENCE, "theme", "dark", importance=6)
    mem_repo.upsert_memory(MemoryCategory.PERSONAL_FACT, "pet", "dog named Max", importance=5)
    mem_repo.upsert_memory(MemoryCategory.PROJECT, "client_project", "Atlas backend", importance=9)

    # Search by key substring
    res1 = mem_repo.search_memories(query="project")
    assert len(res1) == 1
    assert res1[0].key == "client_project"

    # Search by value substring
    res2 = mem_repo.search_memories(query="max")
    assert len(res2) == 1
    assert res2[0].key == "pet"

    # Search by category
    res3 = mem_repo.search_memories(category=MemoryCategory.PREFERENCE)
    assert len(res3) == 1
    assert res3[0].key == "theme"


def test_memory_deletion(
    repo_env: tuple[ConversationRepository, MemoryRepository, Settings]
) -> None:
    _, mem_repo, _ = repo_env

    mem_repo.upsert_memory(MemoryCategory.WORKFLOW, "build_command", "pytest -v")
    assert mem_repo.get_memory("build_command") is not None

    deleted = mem_repo.delete_memory("build_command")
    assert deleted is True
    assert mem_repo.get_memory("build_command") is None

    # Deleting non-existent returns False
    assert mem_repo.delete_memory("non_existent_key") is False
