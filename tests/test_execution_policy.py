"""Tests for ExecutionPolicy process sandboxing and security limits."""

from pathlib import Path
import sys
import pytest

from app.core.exceptions import SecurityError, ToolValidationError
from app.security.execution_policy import ExecutionPolicy, ExecutionRequest
from app.tools.path_guard import PathGuard


@pytest.fixture
def sandbox_env(tmp_path: Path) -> tuple[PathGuard, ExecutionPolicy, Path]:
    allowed_root = tmp_path / "sandbox"
    allowed_root.mkdir()
    guard = PathGuard(allowed_roots=[allowed_root], protected_paths=[])
    policy = ExecutionPolicy(path_guard=guard)
    return guard, policy, allowed_root


def test_trusted_executable_accepted(sandbox_env: tuple[PathGuard, ExecutionPolicy, Path]) -> None:
    _, policy, _ = sandbox_env
    resolved = policy.validate_executable(sys.executable)
    assert resolved == sys.executable


@pytest.mark.parametrize("forbidden", [
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "cmd",
    "cmd.exe",
    "wscript.exe",
    "cscript.exe",
    "mshta.exe",
    "bash",
    "bash.exe",
    "sh",
    "sh.exe",
])
def test_forbidden_executables_strictly_blocked(
    sandbox_env: tuple[PathGuard, ExecutionPolicy, Path], forbidden: str
) -> None:
    _, policy, _ = sandbox_env
    with pytest.raises(SecurityError) as exc_info:
        policy.validate_executable(forbidden)
    assert "strictly forbidden" in str(exc_info.value)


def test_unknown_executable_rejected(sandbox_env: tuple[PathGuard, ExecutionPolicy, Path]) -> None:
    _, policy, _ = sandbox_env
    with pytest.raises(ToolValidationError) as exc_info:
        policy.validate_executable("completely_nonexistent_binary_12345")
    assert "not found on system PATH" in str(exc_info.value)


def test_working_directory_outside_sandbox_rejected(
    sandbox_env: tuple[PathGuard, ExecutionPolicy, Path], tmp_path: Path
) -> None:
    _, policy, _ = sandbox_env
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    req = ExecutionRequest(
        executable=sys.executable,
        args=["-c", "print('hello')"],
        cwd=outside_dir,
    )
    with pytest.raises(ToolValidationError) as exc_info:
        policy.execute(req)
    assert "outside allowed directory boundaries" in str(exc_info.value)


def test_successful_process_execution(
    sandbox_env: tuple[PathGuard, ExecutionPolicy, Path]
) -> None:
    _, policy, sandbox = sandbox_env
    req = ExecutionRequest(
        executable=sys.executable,
        args=["-c", "print('stdout test'); import sys; sys.stderr.write('stderr test')"],
        cwd=sandbox,
    )
    res = policy.execute(req)
    assert res.success is True
    assert res.exit_code == 0
    assert "stdout test" in res.stdout
    assert "stderr test" in res.stderr
    assert not res.timed_out
    assert not res.truncated


def test_nonzero_exit_code_captured(
    sandbox_env: tuple[PathGuard, ExecutionPolicy, Path]
) -> None:
    _, policy, sandbox = sandbox_env
    req = ExecutionRequest(
        executable=sys.executable,
        args=["-c", "import sys; sys.exit(42)"],
        cwd=sandbox,
    )
    res = policy.execute(req)
    assert res.success is False
    assert res.exit_code == 42


def test_output_truncation_enforced(
    sandbox_env: tuple[PathGuard, ExecutionPolicy, Path]
) -> None:
    _, policy, sandbox = sandbox_env
    # Generate 1000 bytes with limit 50 bytes
    req = ExecutionRequest(
        executable=sys.executable,
        args=["-c", "print('A' * 1000)"],
        cwd=sandbox,
        max_output_bytes=50,
    )
    res = policy.execute(req)
    assert res.success is True
    assert res.truncated is True
    assert "[output truncated]" in res.stdout


def test_process_timeout_and_termination(
    sandbox_env: tuple[PathGuard, ExecutionPolicy, Path]
) -> None:
    _, policy, sandbox = sandbox_env
    # Script sleeps for 10 seconds with timeout 0.5s
    req = ExecutionRequest(
        executable=sys.executable,
        args=["-c", "import time; time.sleep(10)"],
        cwd=sandbox,
        timeout_seconds=0.5,
    )
    res = policy.execute(req)
    assert res.success is False
    assert res.timed_out is True
