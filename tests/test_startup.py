"""Unit tests for WindowsStartupManager."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.core.startup import WindowsStartupManager


def test_startup_manager_non_windows_behavior() -> None:
    mgr = WindowsStartupManager(settings=Settings())
    mgr.is_windows = False

    assert mgr.is_autostart_enabled() is False
    assert mgr.enable_autostart() is False
    assert mgr.disable_autostart() is False


def test_startup_manager_enable_and_disable_mocked(tmp_path: Path) -> None:
    mgr = WindowsStartupManager(settings=Settings())
    mgr.is_windows = True

    fake_exe = tmp_path / "LocalAssistant.exe"
    fake_exe.write_text("binary")

    with patch("winreg.OpenKey") as mock_open:
        with patch("winreg.SetValueEx") as mock_set:
            with patch("winreg.DeleteValue") as mock_del:
                enabled = mgr.enable_autostart(exe_path=fake_exe, background_mode=True)
                assert enabled is True
                mock_set.assert_called_once()

                disabled = mgr.disable_autostart()
                assert disabled is True
                mock_del.assert_called_once()
