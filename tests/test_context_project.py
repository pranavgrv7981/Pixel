"""Unit tests for ProjectContextManager and PathGuard integration."""

import pytest
from pathlib import Path
from app.context.database import ContextDatabase
from app.context.models import ContextSource, TrustLevel
from app.context.project import ProjectContextManager
from app.tools.path_guard import PathGuard


@pytest.fixture
def project_mgr(tmp_path: Path) -> ProjectContextManager:
    db = ContextDatabase(db_path=tmp_path / "test_proj.db")
    db.initialize()
    path_guard = PathGuard(allowed_roots=[tmp_path])
    return ProjectContextManager(db=db, path_guard=path_guard)


def test_project_context_manager(project_mgr: ProjectContextManager) -> None:
    # 1. Initially None
    assert project_mgr.get_context_item() is None

    # 2. Set active project
    proj = project_mgr.set_active_project(
        project_name="Gemini Assistant",
        root_path="E:/gemini",
        primary_language="Python",
        description="Local desktop agent",
    )
    assert proj.project_name == "Gemini Assistant"

    # 3. Context Item
    item = project_mgr.get_context_item()
    assert item is not None
    assert item.source == ContextSource.PROJECT_CONTEXT
    assert item.trust_level == TrustLevel.USER
    assert "ACTIVE PROJECT: Gemini Assistant" in item.content
    assert "Primary Language: Python" in item.content

    # 4. Deactivate
    project_mgr.deactivate_active_project()
    assert project_mgr.get_context_item() is None
