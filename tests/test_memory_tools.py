"""Tests for remember_memory, recall_memory, and forget_memory tools."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.core.exceptions import ToolValidationError
from app.memory.manager import MemoryManager
from app.tools.base import RiskLevel
from app.tools.memory import (
    ForgetMemoryTool,
    RecallMemoryTool,
    RememberMemoryTool,
)


@pytest.fixture
def memory_tools(tmp_path: Path) -> tuple[RememberMemoryTool, RecallMemoryTool, ForgetMemoryTool, MemoryManager]:
    db_file = tmp_path / "test_tools.db"
    settings = Settings(memory_database_path=str(db_file))
    mgr = MemoryManager(settings=settings)
    mgr.initialize()

    rem_tool = RememberMemoryTool(memory_manager=mgr, settings=settings)
    rec_tool = RecallMemoryTool(memory_manager=mgr, settings=settings)
    forg_tool = ForgetMemoryTool(memory_manager=mgr, settings=settings)
    return rem_tool, rec_tool, forg_tool, mgr


def test_tool_risk_levels(
    memory_tools: tuple[RememberMemoryTool, RecallMemoryTool, ForgetMemoryTool, MemoryManager]
) -> None:
    rem_tool, rec_tool, forg_tool, _ = memory_tools
    assert rem_tool.risk_level == RiskLevel.LOW
    assert rec_tool.risk_level == RiskLevel.READ
    assert forg_tool.risk_level == RiskLevel.MEDIUM


def test_remember_memory_tool(
    memory_tools: tuple[RememberMemoryTool, RecallMemoryTool, ForgetMemoryTool, MemoryManager]
) -> None:
    rem_tool, _, _, mgr = memory_tools

    res = rem_tool.execute({
        "category": "PROJECT",
        "key": "main_project",
        "value": "Atlas",
        "importance": 9,
    })
    assert res.success is True
    assert res.data["key"] == "main_project"
    assert res.data["value"] == "Atlas"

    saved = mgr.recall(query="Atlas")
    assert len(saved) == 1


def test_remember_memory_tool_invalid_args(
    memory_tools: tuple[RememberMemoryTool, RecallMemoryTool, ForgetMemoryTool, MemoryManager]
) -> None:
    rem_tool, _, _, _ = memory_tools

    # Missing required argument
    with pytest.raises(ToolValidationError):
        rem_tool.validate_args({"category": "PROJECT"})

    # Invalid category
    with pytest.raises(ToolValidationError):
        rem_tool.validate_args({"category": "NON_EXISTENT", "key": "k", "value": "v"})


def test_recall_memory_tool(
    memory_tools: tuple[RememberMemoryTool, RecallMemoryTool, ForgetMemoryTool, MemoryManager]
) -> None:
    rem_tool, rec_tool, _, _ = memory_tools

    rem_tool.execute({"category": "PREFERENCE", "key": "editor", "value": "VS Code"})
    rem_tool.execute({"category": "PROJECT", "key": "main_project", "value": "Atlas"})

    # Recall all
    res = rec_tool.execute({})
    assert res.success is True
    assert res.data["count"] == 2

    # Recall by category
    res_cat = rec_tool.execute({"category": "PREFERENCE"})
    assert res_cat.data["count"] == 1
    assert res_cat.data["memories"][0]["key"] == "editor"


def test_forget_memory_tool(
    memory_tools: tuple[RememberMemoryTool, RecallMemoryTool, ForgetMemoryTool, MemoryManager]
) -> None:
    rem_tool, rec_tool, forg_tool, _ = memory_tools

    rem_tool.execute({"category": "PROJECT", "key": "obsolete_project", "value": "OldApp"})

    # Forget existing
    res = forg_tool.execute({"key": "obsolete_project"})
    assert res.success is True
    assert res.data["deleted"] is True

    # Recall confirms it is gone
    recalled = rec_tool.execute({"query": "OldApp"})
    assert recalled.data["count"] == 0

    # Forget non-existent
    res_missing = forg_tool.execute({"key": "non_existent"})
    assert res_missing.success is False


def test_sql_injection_attempt_is_safely_handled(
    memory_tools: tuple[RememberMemoryTool, RecallMemoryTool, ForgetMemoryTool, MemoryManager]
) -> None:
    rem_tool, rec_tool, _, mgr = memory_tools

    injection_key = "test'; DROP TABLE memories; --"
    injection_val = "' OR '1'='1"

    # Should be safely stored as a literal string via parameterized query
    res = rem_tool.execute({
        "category": "CONTEXT",
        "key": injection_key,
        "value": injection_val,
    })
    assert res.success is True

    # Database and memories table remain intact
    assert mgr.db.check_integrity() is True
    mems = rec_tool.execute({"query": "DROP TABLE"})
    assert mems.data["count"] == 1
