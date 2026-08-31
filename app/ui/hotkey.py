"""Global system-wide hotkey manager for summoning Pixel on Windows."""

import ctypes
from ctypes import wintypes
import sys
import threading
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal

from app.core.logging import get_logger

logger = get_logger("ui.hotkey")

# Win32 Hotkey Modifiers
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


def parse_hotkey_string(hotkey_str: str) -> tuple[int, int]:
    """Parse a shortcut string like 'Alt+P' or 'Ctrl+Alt+Space' into (modifiers, vk_code)."""
    parts = [p.strip() for p in hotkey_str.split("+") if p.strip()]
    modifiers = MOD_NOREPEAT
    vk_code = 0x50  # Default 'P'

    for part in parts[:-1]:
        p_lower = part.lower()
        if p_lower in ("alt", "menu"):
            modifiers |= MOD_ALT
        elif p_lower in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif p_lower in ("shift",):
            modifiers |= MOD_SHIFT
        elif p_lower in ("win", "windows", "super", "meta"):
            modifiers |= MOD_WIN

    key_part = parts[-1].upper()
    if len(key_part) == 1 and ("A" <= key_part <= "Z" or "0" <= key_part <= "9"):
        vk_code = ord(key_part)
    elif key_part.startswith("F") and key_part[1:].isdigit():
        f_num = int(key_part[1:])
        if 1 <= f_num <= 24:
            vk_code = 0x70 + (f_num - 1)
    elif key_part == "SPACE":
        vk_code = 0x20
    elif key_part in ("RETURN", "ENTER"):
        vk_code = 0x0D

    return modifiers, vk_code


class GlobalHotkeyManager(QObject):
    """Manages global Windows system hotkeys using Win32 RegisterHotKey API."""

    hotkey_triggered = Signal()

    def __init__(
        self,
        hotkey_str: str = "Alt+P",
        on_trigger: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.hotkey_str = hotkey_str
        self._on_trigger_cb = on_trigger
        if on_trigger:
            self.hotkey_triggered.connect(on_trigger)

        self._hotkey_id = 101
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._is_running = False
        self._registered = False

    @property
    def is_registered(self) -> bool:
        return self._registered

    def start(self) -> bool:
        """Register hotkey and start background Win32 message pump."""
        if self._is_running:
            return True

        if sys.platform != "win32":
            logger.info("Global hotkeys via Win32 RegisterHotKey are only supported on Windows.")
            self._registered = True
            return True

        self._is_running = True
        init_event = threading.Event()
        success_holder = [False]

        self._thread = threading.Thread(
            target=self._msg_loop,
            args=(init_event, success_holder),
            name="GlobalHotkeyListener",
            daemon=True,
        )
        self._thread.start()

        init_event.wait(timeout=3.0)
        self._registered = success_holder[0]
        if self._registered:
            logger.info("Global hotkey '%s' registered successfully (ID=%d).", self.hotkey_str, self._hotkey_id)
        else:
            logger.warning("Failed to register global hotkey '%s'.", self.hotkey_str)

        return self._registered

    def _msg_loop(self, init_event: threading.Event, success_holder: list[bool]) -> None:
        """Dedicated thread executing GetMessageW loop for WM_HOTKEY."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()
        mods, vk = parse_hotkey_string(self.hotkey_str)

        # Register hotkey on this thread's message queue (hWnd = None)
        res = user32.RegisterHotKey(None, self._hotkey_id, mods, vk)
        success_holder[0] = bool(res)
        init_event.set()

        if not res:
            logger.error("user32.RegisterHotKey failed with error: %d", kernel32.GetLastError())
            self._is_running = False
            return

        msg = wintypes.MSG()
        while self._is_running:
            # Block until message arrives
            b_ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if b_ret == 0 or b_ret == -1:
                break
            if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                logger.info("Global hotkey '%s' pressed! Emitting summon signal.", self.hotkey_str)
                self.hotkey_triggered.emit()

        user32.UnregisterHotKey(None, self._hotkey_id)
        logger.info("Global hotkey '%s' unregistered cleanly.", self.hotkey_str)

    def stop(self) -> None:
        """Unregister global hotkey and stop message pump thread."""
        if not self._is_running:
            return

        self._is_running = False
        if sys.platform == "win32" and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception as err:
                logger.warning("Error posting WM_QUIT to hotkey thread: %s", err)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

        self._registered = False
        self._thread = None
        self._thread_id = None
