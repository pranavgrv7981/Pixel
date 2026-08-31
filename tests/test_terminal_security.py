"""End-to-end integration and security tests for Phase 7 controlled execution tools."""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation, Role
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.execution_policy import ExecutionPolicy, ExecutionResult
from app.security.manager import PermissionManager
from app.security.policies import SecurityPolicy
from app.tools.path_guard import PathGuard
from app.tools.registry import ToolRegistry
from app.tools.terminal import (
    CompileCProgramTool,
    GitStatusTool,
    RunPythonFileTool,
)


@pytest.fixture
def terminal_agent_env(tmp_path: Path) -> tuple[Agent, MagicMock, MagicMock, MagicMock, Path]:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    settings = Settings(filesystem_allowed_roots=[str(sandbox)])
    guard = PathGuard(allowed_roots=[sandbox], protected_paths=[])

    mock_policy = MagicMock(spec=ExecutionPolicy)
    mock_policy.execute.return_value = ExecutionResult(
        success=True,
        exit_code=0,
        stdout="executed successfully",
        stderr="",
        duration_seconds=0.1,
        timed_out=False,
        truncated=False,
        cwd=str(sandbox),
    )

    registry = ToolRegistry()
    registry.register(GitStatusTool(execution_policy=mock_policy, path_guard=guard, settings=settings))
    registry.register(CompileCProgramTool(execution_policy=mock_policy, path_guard=guard, settings=settings))
    registry.register(RunPythonFileTool(execution_policy=mock_policy, path_guard=guard, settings=settings))

    conf_provider = MagicMock(spec=ConfirmationProvider)
    conf_mgr = ConfirmationManager(provider=conf_provider)
    policy = SecurityPolicy()
    perm_mgr = PermissionManager(policy=policy, confirmation_manager=conf_mgr)

    mock_client = MagicMock(spec=OllamaClient)
    mock_client.base_url = "http://localhost:11434"
    mock_client.default_model = "llama3"
    mock_client.check_connection.return_value = True
    mock_client.model_exists.return_value = True

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
        settings=settings,
    )

    return agent, mock_client, conf_provider, mock_policy, sandbox


def test_agent_git_status_auto_approved(
    terminal_agent_env: tuple[Agent, MagicMock, MagicMock, MagicMock, Path]
) -> None:
    agent, mock_client, conf_provider, mock_policy, sandbox = terminal_agent_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "git_status", "arguments": {"repo_path": str(sandbox)}}]),
        ModelResponse("Git status is clean."),
    ]

    with patch("shutil.which", return_value="C:\\Program Files\\Git\\cmd\\git.exe"):
        reply = agent.run("Show git status")
        assert reply == "Git status is clean."
        assert not conf_provider.request_confirmation.called
        assert mock_policy.execute.called


def test_agent_compile_c_confirmed_by_user(
    terminal_agent_env: tuple[Agent, MagicMock, MagicMock, MagicMock, Path]
) -> None:
    agent, mock_client, conf_provider, mock_policy, sandbox = terminal_agent_env
    conf_provider.request_confirmation.return_value = True

    c_file = sandbox / "test.c"
    c_file.write_text("int main(){return 0;}", encoding="utf-8")
    ext = ".exe" if sys.platform == "win32" else ""
    out_bin = sandbox / f"test{ext}"
    out_bin.write_bytes(b"\x00")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "compile_c_program", "arguments": {"source_path": str(c_file)}}]),
        ModelResponse("Compiled test.c successfully."),
    ]

    with patch("shutil.which", return_value="C:\\msys64\\ucrt64\\bin\\gcc.exe"):
        reply = agent.run("Compile test.c")
        assert reply == "Compiled test.c successfully."
        assert conf_provider.request_confirmation.called
        assert mock_policy.execute.called


def test_agent_compile_c_declined_by_user(
    terminal_agent_env: tuple[Agent, MagicMock, MagicMock, MagicMock, Path]
) -> None:
    agent, mock_client, conf_provider, mock_policy, sandbox = terminal_agent_env
    conf_provider.request_confirmation.return_value = False

    c_file = sandbox / "test.c"
    c_file.write_text("int main(){return 0;}", encoding="utf-8")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "compile_c_program", "arguments": {"source_path": str(c_file)}}]),
        ModelResponse("Compilation was canceled."),
    ]

    reply = agent.run("Compile test.c")
    assert reply == "Compilation was canceled."
    assert conf_provider.request_confirmation.called
    assert not mock_policy.execute.called


def test_agent_run_python_confirmed_by_user(
    terminal_agent_env: tuple[Agent, MagicMock, MagicMock, MagicMock, Path]
) -> None:
    agent, mock_client, conf_provider, mock_policy, sandbox = terminal_agent_env
    conf_provider.request_confirmation.return_value = True

    py_file = sandbox / "app.py"
    py_file.write_text("print('hello')", encoding="utf-8")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "run_python_file", "arguments": {"script_path": str(py_file)}}]),
        ModelResponse("App executed successfully."),
    ]

    reply = agent.run("Run app.py")
    assert reply == "App executed successfully."
    assert conf_provider.request_confirmation.called
    assert mock_policy.execute.called


def test_agent_run_python_declined_by_user(
    terminal_agent_env: tuple[Agent, MagicMock, MagicMock, MagicMock, Path]
) -> None:
    agent, mock_client, conf_provider, mock_policy, sandbox = terminal_agent_env
    conf_provider.request_confirmation.return_value = False

    py_file = sandbox / "app.py"
    py_file.write_text("print('hello')", encoding="utf-8")

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "run_python_file", "arguments": {"script_path": str(py_file)}}]),
        ModelResponse("Execution was canceled by user."),
    ]

    reply = agent.run("Run app.py")
    assert reply == "Execution was canceled by user."
    assert conf_provider.request_confirmation.called
    assert not mock_policy.execute.called


def test_agent_arbitrary_path_rejected_before_confirmation(
    terminal_agent_env: tuple[Agent, MagicMock, MagicMock, MagicMock, Path]
) -> None:
    agent, mock_client, conf_provider, mock_policy, _ = terminal_agent_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{"name": "run_python_file", "arguments": {"script_path": "C:\\Windows\\System32\\calc.py"}}]),
        ModelResponse("I cannot execute scripts outside allowed roots."),
    ]

    reply = agent.run("Run script in Windows")
    assert reply == "I cannot execute scripts outside allowed roots."
    assert not conf_provider.request_confirmation.called
    assert not mock_policy.execute.called

    msgs = agent.conversation.get_messages()
    assert msgs[2].role == Role.TOOL
    assert "outside allowed directory boundaries" in msgs[2].content or "does not exist" in msgs[2].content
