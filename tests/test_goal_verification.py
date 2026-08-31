"""Unit tests for ActionVerifier host state inspection."""

import pytest
from pathlib import Path
from app.agent.verifier import ActionVerifier
from app.tools.base import ToolResult


@pytest.fixture
def verifier() -> ActionVerifier:
    return ActionVerifier()


def test_verify_file_creation_exists(tmp_path: Path, verifier: ActionVerifier) -> None:
    test_file = tmp_path / "created.txt"
    test_file.write_text("hello world", encoding="utf-8")

    res = ToolResult(success=True, data={"bytes_written": 11})
    verification = verifier.verify_tool_action("write_text_file", {"path": str(test_file)}, res)
    assert verification.verified is True
    assert verification.goal_achieved is True
    assert "11 bytes" in verification.details


def test_verify_file_creation_missing(tmp_path: Path, verifier: ActionVerifier) -> None:
    missing_file = tmp_path / "ghost.txt"
    res = ToolResult(success=True, data={"bytes_written": 50})
    verification = verifier.verify_tool_action("write_text_file", {"path": str(missing_file)}, res)
    assert verification.verified is False
    assert verification.goal_achieved is False
    assert "File missing post-write" in verification.discrepancies


def test_verify_file_deletion(tmp_path: Path, verifier: ActionVerifier) -> None:
    del_file = tmp_path / "del.txt"
    # File does not exist on disk
    res = ToolResult(success=True)
    verification = verifier.verify_tool_action("delete_file", {"path": str(del_file)}, res)
    assert verification.verified is True
    assert verification.goal_achieved is True


def test_verify_pytest_exit_code(verifier: ActionVerifier) -> None:
    # 1. Success
    res_pass = ToolResult(success=True, data={"exit_code": 0, "passed": 10})
    ver_pass = verifier.verify_tool_action("run_pytest", {}, res_pass)
    assert ver_pass.verified is True
    assert ver_pass.goal_achieved is True

    # 2. Failure
    res_fail = ToolResult(success=True, data={"exit_code": 1, "failed": 2})
    ver_fail = verifier.verify_tool_action("run_pytest", {}, res_fail)
    assert ver_fail.goal_achieved is False
