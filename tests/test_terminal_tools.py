"""Tests for Phase 7 controlled terminal tools."""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest

from app.core.exceptions import ToolValidationError
from app.security.execution_policy import ExecutionPolicy, ExecutionResult
from app.tools.path_guard import PathGuard
from app.tools.terminal import (
    CompileCProgramTool,
    GitDiffTool,
    GitStatusTool,
    RunCProgramTool,
    RunPytestTool,
    RunPythonFileTool,
)


@pytest.fixture
def sandbox_env(tmp_path: Path) -> tuple[PathGuard, MagicMock, Path]:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    guard = PathGuard(allowed_roots=[sandbox], protected_paths=[])
    mock_policy = MagicMock(spec=ExecutionPolicy)
    mock_policy.execute.return_value = ExecutionResult(
        success=True,
        exit_code=0,
        stdout="mocked stdout",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
        truncated=False,
        cwd=str(sandbox),
    )
    return guard, mock_policy, sandbox


def test_git_status_tool(sandbox_env: tuple[PathGuard, MagicMock, Path]) -> None:
    guard, mock_policy, sandbox = sandbox_env
    tool = GitStatusTool(execution_policy=mock_policy, path_guard=guard)

    with patch("shutil.which", return_value="C:\\Program Files\\Git\\cmd\\git.exe"):
        res = tool.execute({"repo_path": str(sandbox)})
        assert res.success is True
        assert res.data["exit_code"] == 0
        req = mock_policy.execute.call_args[0][0]
        assert req.args == ["status", "--short"]


def test_git_diff_tool(sandbox_env: tuple[PathGuard, MagicMock, Path]) -> None:
    guard, mock_policy, sandbox = sandbox_env
    tool = GitDiffTool(execution_policy=mock_policy, path_guard=guard)

    with patch("shutil.which", return_value="C:\\Program Files\\Git\\cmd\\git.exe"):
        res = tool.execute({"repo_path": str(sandbox), "staged": True})
        assert res.success is True
        req = mock_policy.execute.call_args[0][0]
        assert req.args == ["diff", "--staged"]


def test_compile_c_program_rejects_non_c_file(
    sandbox_env: tuple[PathGuard, MagicMock, Path]
) -> None:
    guard, mock_policy, sandbox = sandbox_env
    py_file = sandbox / "test.py"
    py_file.write_text("print(1)", encoding="utf-8")

    tool = CompileCProgramTool(execution_policy=mock_policy, path_guard=guard)
    with pytest.raises(ToolValidationError) as exc_info:
        tool.validate_args({"source_path": str(py_file)})
    assert "must have a .c extension" in str(exc_info.value)


def test_compile_c_program_rejects_traversal_output_name(
    sandbox_env: tuple[PathGuard, MagicMock, Path]
) -> None:
    guard, mock_policy, sandbox = sandbox_env
    c_file = sandbox / "main.c"
    c_file.write_text("int main() { return 0; }", encoding="utf-8")

    tool = CompileCProgramTool(execution_policy=mock_policy, path_guard=guard)
    with pytest.raises(ToolValidationError) as exc_info:
        tool.validate_args({"source_path": str(c_file), "output_name": "../evil.exe"})
    assert "cannot contain path separators" in str(exc_info.value)


def test_compile_c_program_success(
    sandbox_env: tuple[PathGuard, MagicMock, Path]
) -> None:
    guard, mock_policy, sandbox = sandbox_env
    c_file = sandbox / "main.c"
    c_file.write_text("int main() { return 0; }", encoding="utf-8")

    tool = CompileCProgramTool(execution_policy=mock_policy, path_guard=guard)

    # Simulate post-operation binary creation
    ext = ".exe" if sys.platform == "win32" else ""
    out_bin = sandbox / f"main{ext}"
    out_bin.write_bytes(b"\x00")

    with patch("shutil.which", return_value="C:\\msys64\\ucrt64\\bin\\gcc.exe"):
        res = tool.execute({"source_path": str(c_file)})
        assert res.success is True
        assert res.data["output_binary"] == str(out_bin)
        req = mock_policy.execute.call_args[0][0]
        assert req.args == [str(c_file), "-o", str(out_bin)]


def test_run_python_file_success(
    sandbox_env: tuple[PathGuard, MagicMock, Path]
) -> None:
    guard, mock_policy, sandbox = sandbox_env
    script = sandbox / "script.py"
    script.write_text("print('hello')", encoding="utf-8")

    tool = RunPythonFileTool(execution_policy=mock_policy, path_guard=guard)
    res = tool.execute({"script_path": str(script), "args": ["--arg1", "val1"]})
    assert res.success is True
    req = mock_policy.execute.call_args[0][0]
    assert req.args == [str(script), "--arg1", "val1"]


def test_run_python_file_rejects_non_py(
    sandbox_env: tuple[PathGuard, MagicMock, Path]
) -> None:
    guard, mock_policy, sandbox = sandbox_env
    txt = sandbox / "notes.txt"
    txt.write_text("notes", encoding="utf-8")

    tool = RunPythonFileTool(execution_policy=mock_policy, path_guard=guard)
    with pytest.raises(ToolValidationError) as exc_info:
        tool.validate_args({"script_path": str(txt)})
    assert "must have a .py extension" in str(exc_info.value)


def test_run_pytest_tool(
    sandbox_env: tuple[PathGuard, MagicMock, Path]
) -> None:
    guard, mock_policy, sandbox = sandbox_env
    tests_dir = sandbox / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_sample.py"
    test_file.write_text("def test_ok(): pass", encoding="utf-8")

    tool = RunPytestTool(execution_policy=mock_policy, path_guard=guard)
    res = tool.execute({"project_path": str(sandbox), "test_target": "tests/test_sample.py"})
    assert res.success is True
    req = mock_policy.execute.call_args[0][0]
    assert req.args == ["-m", "pytest", "tests\\test_sample.py" if sys.platform == "win32" else "tests/test_sample.py"]


def test_run_c_program_tool(
    sandbox_env: tuple[PathGuard, MagicMock, Path]
) -> None:
    guard, mock_policy, sandbox = sandbox_env
    ext = ".exe" if sys.platform == "win32" else ""
    bin_file = sandbox / f"prog{ext}"
    bin_file.write_bytes(b"\x00")

    tool = RunCProgramTool(execution_policy=mock_policy, path_guard=guard)
    res = tool.execute({"executable_path": str(bin_file), "args": ["1", "2"]})
    assert res.success is True
    req = mock_policy.execute.call_args[0][0]
    assert req.args == ["1", "2"]
