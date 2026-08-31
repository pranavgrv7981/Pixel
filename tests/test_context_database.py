"""Unit tests for ContextDatabase persistence layer."""

import pytest
from pathlib import Path
from app.context.database import ContextDatabase
from app.context.models import ProjectContext, ResponseStyle, UserProfile


@pytest.fixture
def temp_db(tmp_path: Path) -> ContextDatabase:
    db_path = tmp_path / "test_context.db"
    db = ContextDatabase(db_path=db_path)
    db.initialize()
    return db


def test_conversation_summary_crud(temp_db: ContextDatabase) -> None:
    # 1. Nonexistent returns None
    assert temp_db.get_summary("conv-123") is None

    # 2. Upsert summary
    rec = temp_db.upsert_summary(
        conversation_id="conv-123",
        summary="User discussed Python async and threading.",
        messages_summarized_count=10,
        last_message_index=9,
        topics=["Python async", "Threading"],
        decisions=["Use asyncio for network I/O"],
    )
    assert rec.conversation_id == "conv-123"
    assert rec.messages_summarized_count == 10
    assert rec.topics == ["Python async", "Threading"]
    assert rec.decisions == ["Use asyncio for network I/O"]

    # 3. Retrieve
    fetched = temp_db.get_summary("conv-123")
    assert fetched is not None
    assert fetched.summary == "User discussed Python async and threading."

    # 4. Update
    temp_db.upsert_summary(
        conversation_id="conv-123",
        summary="Updated summary.",
        messages_summarized_count=15,
        last_message_index=14,
    )
    updated = temp_db.get_summary("conv-123")
    assert updated is not None
    assert updated.summary == "Updated summary."
    assert updated.messages_summarized_count == 15

    # 5. Delete
    assert temp_db.delete_summary("conv-123") is True
    assert temp_db.get_summary("conv-123") is None


def test_user_profile_crud(temp_db: ContextDatabase) -> None:
    # 1. Default profile
    p_default = temp_db.get_user_profile()
    assert p_default.response_style == ResponseStyle.BALANCED
    assert p_default.preferred_language == "English"

    # 2. Save profile
    p_custom = UserProfile(
        preferred_name="Bob",
        response_style=ResponseStyle.CONCISE,
        preferred_language="Spanish",
        technical_level="expert",
        custom_instructions="Focus on performance.",
    )
    saved = temp_db.save_user_profile(p_custom)
    assert saved.preferred_name == "Bob"
    assert saved.response_style == ResponseStyle.CONCISE
    assert saved.preferred_language == "Spanish"
    assert saved.technical_level == "expert"
    assert saved.custom_instructions == "Focus on performance."

    # 3. Retrieve persistent profile
    retrieved = temp_db.get_user_profile()
    assert retrieved.preferred_name == "Bob"
    assert retrieved.response_style == ResponseStyle.CONCISE


def test_project_context_crud(temp_db: ContextDatabase) -> None:
    # 1. Initially no active project
    assert temp_db.get_active_project() is None

    # 2. Register active project
    proj1 = ProjectContext(
        id="proj-1",
        project_name="Alpha Engine",
        root_path="E:/alpha",
        primary_language="C++",
        description="Low latency engine",
        is_active=True,
    )
    temp_db.set_active_project(proj1)

    active = temp_db.get_active_project()
    assert active is not None
    assert active.project_name == "Alpha Engine"
    assert active.primary_language == "C++"

    # 3. Register second project -> becomes active and deactivates first
    proj2 = ProjectContext(
        id="proj-2",
        project_name="Beta Assistant",
        root_path="E:/beta",
        primary_language="Python",
        description="AI assistant",
        is_active=True,
    )
    temp_db.set_active_project(proj2)

    active2 = temp_db.get_active_project()
    assert active2 is not None
    assert active2.project_name == "Beta Assistant"

    # 4. List projects
    all_projs = temp_db.list_projects()
    assert len(all_projs) == 2
    assert all_projs[0].id == "proj-2"

    # 5. Delete project
    assert temp_db.delete_project("proj-1") is True
    assert len(temp_db.list_projects()) == 1
