"""Unit tests for UserProfileManager and personalization."""

import pytest
from pathlib import Path
from app.context.database import ContextDatabase
from app.context.models import ContextSource, ResponseStyle, TrustLevel
from app.context.profile import UserProfileManager


@pytest.fixture
def profile_mgr(tmp_path: Path) -> UserProfileManager:
    db = ContextDatabase(db_path=tmp_path / "test_prof.db")
    db.initialize()
    return UserProfileManager(db=db)


def test_profile_update_and_context_item(profile_mgr: UserProfileManager) -> None:
    # 1. Update
    updated = profile_mgr.update_profile(
        preferred_name="Charlie",
        response_style=ResponseStyle.CONCISE,
        technical_level="expert",
        custom_instructions="Be brief and omit intro.",
    )
    assert updated.preferred_name == "Charlie"
    assert updated.response_style == ResponseStyle.CONCISE

    # 2. Context Item conversion
    item = profile_mgr.get_context_item()
    assert item is not None
    assert item.source == ContextSource.USER_PROFILE
    assert item.trust_level == TrustLevel.USER
    assert "Charlie" in item.content
    assert "CONCISE" in item.content
    assert "EXPERT" in item.content
