"""Tests for Phase 6 application tools in app/tools/applications.py."""

from unittest.mock import MagicMock, patch
import pytest

from app.core.exceptions import ToolValidationError
from app.tools.applications import (
    ApplicationDefinition,
    ApplicationRegistry,
    CloseApplicationTool,
    IsApplicationRunningTool,
    OpenApplicationTool,
)
from app.tools.system import SystemProvider


@pytest.fixture
def registry() -> ApplicationRegistry:
    return ApplicationRegistry()


@pytest.fixture
def mock_sys_provider() -> MagicMock:
    provider = MagicMock(spec=SystemProvider)
    provider.list_processes.return_value = [
        {"pid": 1234, "name": "notepad.exe", "parent_pid": 100, "threads": 2}
    ]
    return provider


def test_application_registry_defaults(registry: ApplicationRegistry) -> None:
    """Verify default applications and aliases in whitelist."""
    assert registry.is_whitelisted("notepad")
    assert registry.is_whitelisted("calculator")
    assert registry.is_whitelisted("calc")
    assert registry.is_whitelisted("vscode")
    assert registry.is_whitelisted("code")
    assert registry.is_whitelisted("chrome")
    assert registry.is_whitelisted("edge")
    assert registry.is_whitelisted("paint")


def test_application_registry_rejects_unknown_and_malicious(registry: ApplicationRegistry) -> None:
    """Verify registry rejects unauthorized executables and shell injections."""
    assert not registry.is_whitelisted("powershell")
    assert not registry.is_whitelisted("powershell.exe")
    assert not registry.is_whitelisted("cmd")
    assert not registry.is_whitelisted("cmd.exe")
    assert not registry.is_whitelisted("notepad; dir")
    assert not registry.is_whitelisted("calc & whoami")
    assert not registry.is_whitelisted("C:\\evil.exe")
    assert not registry.is_whitelisted("arbitrary_tool")


def test_open_application_unknown_app_rejected_early(registry: ApplicationRegistry) -> None:
    """Verify open_application raises ToolValidationError on unauthorized application."""
    tool = OpenApplicationTool(registry=registry)
    with pytest.raises(ToolValidationError) as exc_info:
        tool.validate_args({"app_name": "malicious_app"})
    assert "not in the approved whitelist" in str(exc_info.value)


def test_open_application_shell_injection_rejected_early(registry: ApplicationRegistry) -> None:
    """Verify open_application blocks shell command injection attempts."""
    tool = OpenApplicationTool(registry=registry)
    with pytest.raises(ToolValidationError) as exc_info:
        tool.validate_args({"app_name": "notepad; calc.exe"})
    assert "not in the approved whitelist" in str(exc_info.value)


def test_open_application_success_and_verification(
    registry: ApplicationRegistry, mock_sys_provider: MagicMock
) -> None:
    """Verify open_application launches without shell and verifies process appearance."""
    tool = OpenApplicationTool(registry=registry, system_provider=mock_sys_provider)

    with patch("shutil.which", return_value="C:\\Windows\\notepad.exe"), \
         patch("subprocess.Popen") as mock_popen:
        res = tool.execute({"app_name": "notepad"})
        assert res.success is True
        assert res.data["verified"] is True
        assert 1234 in res.data["pids"]
        # Verify shell=False is strictly enforced
        mock_popen.assert_called_once_with(["C:\\Windows\\notepad.exe"], shell=False)


def test_close_application_not_running(
    registry: ApplicationRegistry, mock_sys_provider: MagicMock
) -> None:
    """Verify close_application cleanly reports if app is not running."""
    mock_sys_provider.list_processes.return_value = []  # No processes
    tool = CloseApplicationTool(registry=registry, system_provider=mock_sys_provider)

    res = tool.execute({"app_name": "notepad"})
    assert res.success is True
    assert res.data["status"] == "not_running"
    assert "not currently running" in res.message


def test_close_application_success_and_verification(
    registry: ApplicationRegistry, mock_sys_provider: MagicMock
) -> None:
    """Verify close_application terminates matching PID and verifies process exit."""
    # First call: process is running (PID 1234); subsequent calls: process is gone
    mock_sys_provider.list_processes.side_effect = [
        [{"pid": 1234, "name": "notepad.exe"}],
        [],
    ]
    tool = CloseApplicationTool(registry=registry, system_provider=mock_sys_provider)

    with patch("subprocess.run") as mock_run:
        res = tool.execute({"app_name": "notepad"})
        assert res.success is True
        assert res.data["verified"] is True
        assert 1234 in res.data["closed_pids"]
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["taskkill", "/PID", "1234"]


def test_is_application_running(
    registry: ApplicationRegistry, mock_sys_provider: MagicMock
) -> None:
    """Verify is_application_running reports correct state for whitelisted apps."""
    tool = IsApplicationRunningTool(registry=registry, system_provider=mock_sys_provider)

    res_notepad = tool.execute({"app_name": "notepad"})
    assert res_notepad.success is True
    assert res_notepad.data["running"] is True
    assert res_notepad.data["process_count"] == 1

    res_calc = tool.execute({"app_name": "calculator"})
    assert res_calc.success is True
    assert res_calc.data["running"] is False
    assert res_calc.data["process_count"] == 0
