"""Windows login autostart registration manager using user-level registry."""

from pathlib import Path
import sys
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("core.startup")

REGISTRY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REGISTRY_VALUE_NAME = "LocalAIPersonalAssistant"


class WindowsStartupManager:
    """Manages optional, user-level Windows login autostart via HKCU Run registry key."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings: Settings = settings or get_settings()
        self.is_windows: bool = sys.platform == "win32"

    def is_autostart_enabled(self) -> bool:
        """Check if the assistant is registered in HKCU Run registry key."""
        if not self.is_windows:
            return False

        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_RUN_KEY, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, APP_REGISTRY_VALUE_NAME)
                    return bool(val)
                except FileNotFoundError:
                    return False
        except Exception as err:
            logger.debug("Could not query Windows startup registry: %s", err)
            return False

    def enable_autostart(self, exe_path: Optional[Path] = None, background_mode: bool = True) -> bool:
        """Register the assistant executable in HKCU Run key to launch on user login."""
        if not self.is_windows:
            logger.warning("Windows startup registration is only supported on Windows.")
            return False

        try:
            import winreg

            target_exe = exe_path or Path(sys.executable).resolve()
            # If running via python.exe, target python.exe with main.py
            if getattr(sys, "frozen", False):
                command = f'"{target_exe}"'
            else:
                main_py = (self.settings.project_root / "main.py").resolve()
                command = f'"{target_exe}" "{main_py}"'

            if background_mode:
                command += " --background"

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, command)

            logger.info("Registered Windows autostart: %s", command)
            return True
        except Exception as err:
            logger.error("Failed to register Windows autostart: %s", err)
            return False

    def disable_autostart(self) -> bool:
        """Remove the assistant registration from HKCU Run key."""
        if not self.is_windows:
            return False

        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, APP_REGISTRY_VALUE_NAME)
                    logger.info("Unregistered Windows autostart.")
                    return True
                except FileNotFoundError:
                    return True
        except Exception as err:
            logger.warning("Could not remove Windows autostart registration: %s", err)
            return False
