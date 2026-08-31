"""Tests for knowledge tools schemas, risk levels, and argument validation."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.core.exceptions import ToolValidationError
from app.knowledge.manager import KnowledgeManager
from app.tools.base import RiskLevel
from app.tools.knowledge import (
    IndexDirectoryTool,
    IndexDocumentTool,
    ListIndexedDocumentsTool,
    RemoveDocumentTool,
    SearchKnowledgeTool,
)
from app.tools.path_guard import PathGuard


@pytest.fixture
def knowledge_tools(tmp_path: Path) -> tuple[SearchKnowledgeTool, ListIndexedDocumentsTool, IndexDocumentTool, IndexDirectoryTool, RemoveDocumentTool, Path]:
    allowed_dir = tmp_path / "allowed_docs"
    allowed_dir.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "test_tools.db"

    settings = Settings(
        filesystem_allowed_roots=[str(allowed_dir)],
        knowledge_database_path=str(db_file),
    )
    guard = PathGuard(settings=settings)
    km = KnowledgeManager(settings=settings, path_guard=guard)
    km.initialize()

    search_tool = SearchKnowledgeTool(knowledge_manager=km, settings=settings)
    list_tool = ListIndexedDocumentsTool(knowledge_manager=km, settings=settings)
    idx_doc_tool = IndexDocumentTool(knowledge_manager=km, settings=settings)
    idx_dir_tool = IndexDirectoryTool(knowledge_manager=km, settings=settings)
    rem_tool = RemoveDocumentTool(knowledge_manager=km, settings=settings)

    return search_tool, list_tool, idx_doc_tool, idx_dir_tool, rem_tool, allowed_dir


def test_tool_risk_levels(knowledge_tools: tuple) -> None:
    search_tool, list_tool, idx_doc_tool, idx_dir_tool, rem_tool, _ = knowledge_tools
    assert search_tool.risk_level == RiskLevel.READ
    assert list_tool.risk_level == RiskLevel.READ
    assert idx_doc_tool.risk_level == RiskLevel.MEDIUM
    assert idx_dir_tool.risk_level == RiskLevel.MEDIUM
    assert rem_tool.risk_level == RiskLevel.MEDIUM


def test_index_and_search_tools(knowledge_tools: tuple) -> None:
    search_tool, list_tool, idx_doc_tool, _, _, allowed_dir = knowledge_tools

    doc_file = allowed_dir / "tutorial.txt"
    doc_file.write_text("Detailed guide on setting up asynchronous Python tasks.", encoding="utf-8")

    # Index document via tool
    res_idx = idx_doc_tool.execute({"path": str(doc_file)})
    assert res_idx.success is True
    assert res_idx.data["documents_indexed"] == 1

    # List indexed documents
    res_list = list_tool.execute({})
    assert res_list.success is True
    assert res_list.data["count"] == 1
    assert res_list.data["documents"][0]["file_name"] == "tutorial.txt"

    # Search knowledge
    res_search = search_tool.execute({"query": "asynchronous Python tasks"})
    assert res_search.success is True
    assert res_search.data["count"] >= 1
    assert "tutorial.txt" in res_search.data["context_text"]


def test_search_tool_validation_missing_query(knowledge_tools: tuple) -> None:
    search_tool, _, _, _, _, _ = knowledge_tools
    with pytest.raises(ToolValidationError):
        search_tool.validate_args({})
