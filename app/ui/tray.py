"""System tray resident icon and tray menu integration for background assistant operation."""

from typing import Any, Callable, Optional
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
    QWidget,
)

from app.core.logging import get_logger

logger = get_logger("ui.tray")


def create_status_icon(is_active: bool = True) -> QIcon:
    """Dynamically generate a crisp 32x32 status icon for the system tray."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Outer circle
    bg_color = QColor("#0d0f18")
    painter.setBrush(bg_color)
    painter.setPen(QColor("#2b324c"))
    painter.drawEllipse(2, 2, 28, 28)

    # Status indicator dot (Cyan when active)
    status_color = QColor("#00f2fe") if is_active else QColor("#f59e0b")
    painter.setBrush(status_color)
    painter.setPen(status_color)
    painter.drawEllipse(10, 10, 12, 12)

    painter.end()
    return QIcon(pixmap)


class AssistantTrayIcon(QSystemTrayIcon):
    """System tray icon maintaining background residency and quick action menu for Pixel."""

    def __init__(
        self,
        main_window: QWidget,
        automation_toggle_callback: Optional[Callable[[bool], None]] = None,
        open_automation_callback: Optional[Callable[[], None]] = None,
        voice_wake_toggle_callback: Optional[Callable[[bool], None]] = None,
        new_chat_callback: Optional[Callable[[], None]] = None,
        open_settings_callback: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.main_window = main_window
        self.automation_toggle_callback = automation_toggle_callback
        self.open_automation_callback = open_automation_callback
        self.voice_wake_toggle_callback = voice_wake_toggle_callback
        self.new_chat_callback = new_chat_callback
        self.open_settings_callback = open_settings_callback

        self._automation_enabled = True
        self._voice_wake_enabled = False
        self.setIcon(create_status_icon(is_active=True))
        self.setToolTip("Pixel AI Assistant (🟢 Active)")

        self._setup_menu()
        self.activated.connect(self._on_tray_activated)

    def _setup_menu(self) -> None:
        menu = QMenu()

        # 1. Open Pixel (Primary action)
        self.open_action = QAction("Open Pixel", self)
        font = self.open_action.font()
        font.setBold(True)
        self.open_action.setFont(font)
        self.open_action.triggered.connect(self.show_main_window)
        menu.addAction(self.open_action)

        # 2. New Chat
        self.new_chat_action = QAction("New Chat", self)
        self.new_chat_action.triggered.connect(self._handle_new_chat)
        menu.addAction(self.new_chat_action)

        menu.addSeparator()

        # 3. Voice Wake On/Off Toggle
        self.voice_wake_action = QAction("Voice Wake", self)
        self.voice_wake_action.setCheckable(True)
        self.voice_wake_action.setChecked(self._voice_wake_enabled)
        self.voice_wake_action.triggered.connect(self._toggle_voice_wake)
        menu.addAction(self.voice_wake_action)

        # 4. Settings
        self.settings_action = QAction("Settings...", self)
        self.settings_action.triggered.connect(self._handle_open_settings)
        menu.addAction(self.settings_action)

        # 5. Automation / Background Activity
        if self.open_automation_callback:
            self.auto_action = QAction("Automation Center...", self)
            self.auto_action.triggered.connect(self.open_automation_callback)
            menu.addAction(self.auto_action)

        self.pause_action = QAction("Pause Background Activity", self)
        self.pause_action.triggered.connect(self._toggle_automation)
        menu.addAction(self.pause_action)

        menu.addSeparator()

        # 6. Exit Pixel
        self.quit_action = QAction("Exit Pixel", self)
        self.quit_action.triggered.connect(self._quit_application)
        menu.addAction(self.quit_action)

        self.setContextMenu(menu)

    def set_voice_wake_checked(self, enabled: bool) -> None:
        """Update check state of Voice Wake action."""
        self._voice_wake_enabled = enabled
        self.voice_wake_action.setChecked(enabled)

    def _toggle_voice_wake(self, checked: bool) -> None:
        self._voice_wake_enabled = checked
        logger.info("Tray toggled Voice Wake: %s", checked)
        if self.voice_wake_toggle_callback:
            self.voice_wake_toggle_callback(checked)

    def _handle_new_chat(self) -> None:
        self.show_main_window()
        if self.new_chat_callback:
            self.new_chat_callback()
        elif hasattr(self.main_window, "controller"):
            self.main_window.controller.new_conversation()

    def _handle_open_settings(self) -> None:
        self.show_main_window()
        if self.open_settings_callback:
            self.open_settings_callback()
        elif hasattr(self.main_window, "_open_settings"):
            self.main_window._open_settings()

    def update_automation_status(self, enabled: bool) -> None:
        """Update visual tray icon and menu text based on automation state."""
        self._automation_enabled = enabled
        self.setIcon(create_status_icon(is_active=enabled))
        status_text = "🟢 Active" if enabled else "⏸ Paused"
        self.setToolTip(f"Pixel AI Assistant ({status_text})")
        self.pause_action.setText("Pause Background Activity" if enabled else "Resume Background Activity")

    def _toggle_automation(self) -> None:
        new_state = not self._automation_enabled
        self.update_automation_status(new_state)
        if self.automation_toggle_callback:
            self.automation_toggle_callback(new_state)

    def show_main_window(self) -> None:
        """Restore, ensure visible, and raise the main application window."""
        if hasattr(self.main_window, "summon_pixel"):
            self.main_window.summon_pixel("tray")
        else:
            if hasattr(self.main_window, "ensure_visible_on_screen"):
                self.main_window.ensure_visible_on_screen()
            self.main_window.show()
            self.main_window.showNormal()
            self.main_window.activateWindow()
            self.main_window.raise_()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_main_window()

    def show_notification(self, title: str, message: str, severity: str = "info") -> None:
        """Display an OS-native system tray toast balloon notification."""
        icon_type = QSystemTrayIcon.Information
        if severity == "warning":
            icon_type = QSystemTrayIcon.Warning
        elif severity == "critical" or severity == "error":
            icon_type = QSystemTrayIcon.Critical

        self.showMessage(title, message, icon_type, 4000)

    def _quit_application(self) -> None:
        """Cleanly exit the entire assistant application."""
        logger.info("User requested full application exit from system tray.")
        self.hide()
        QApplication.quit()
