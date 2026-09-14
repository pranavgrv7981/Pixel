"""Main application window coordinating UI layout, menus, controllers, animations, and diagnostics."""

import threading
from typing import Any, Optional
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.controller import AssistantController
from app.ui.models import UIState
from app.ui.theme import (
    APPLICATION_STYLESHEET,
    COLOR_ACCENT,
    COLOR_BG_DARK,
    COLOR_BG_PANEL,
    COLOR_BG_SURFACE,
    COLOR_BORDER_SOLID,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)
from app.ui.widgets.automation_dialog import AutomationDialog
from app.ui.widgets.chat_view import ChatView
from app.ui.widgets.confirmation_dialog import ConfirmationDialog
from app.ui.widgets.diagnostics_drawer import DiagnosticsDrawer
from app.ui.widgets.input_bar import InputBar
from app.ui.widgets.knowledge_dialog import KnowledgeDialog
from app.ui.widgets.memory_dialog import MemoryDialog
from app.ui.widgets.pixel_core import PixelCoreState
from app.ui.widgets.settings_dialog import SettingsDialog
from app.ui.widgets.sidebar import ConversationSidebar
from app.ui.widgets.status_bar import SystemStatusBar
from app.ui.widgets.tasks_dialog import TasksDialog


class MainWindow(QMainWindow):
    """Primary desktop application window for Pixel - The Living Personal AI Assistant."""

    def __init__(
        self,
        controller: AssistantController,
        voice_controller: Optional[Any] = None,
        tts_controller: Optional[Any] = None,
        task_controller: Optional[Any] = None,
        automation_controller: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.voice_controller = voice_controller
        self.tts_controller = tts_controller
        self.task_controller = task_controller
        self.automation_controller = automation_controller

        self.setWindowTitle(f"Local AI Personal Assistant - {controller.settings.app_name}")
        self.resize(1150, 780)
        self.setMinimumSize(850, 550)
        self.setStyleSheet(APPLICATION_STYLESHEET)

        self._setup_menu()
        self._setup_ui()
        self._wire_signals()
        self.ensure_visible_on_screen()

        # Polling timer for status refresh (every 30 seconds)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.controller.check_backend_status)
        self.status_timer.start(30000)

        # Initial refresh
        QTimer.singleShot(100, self._initial_startup)

    def ensure_visible_on_screen(self) -> None:
        """Validate window geometry against all displays and center if outside or too close to edge."""
        from PySide6.QtGui import QGuiApplication

        _MARGIN = 50  # px safety margin from screen edge
        current_geo = self.frameGeometry()

        centre = current_geo.center()
        screen = None
        for s in QGuiApplication.screens():
            if s.availableGeometry().contains(centre):
                screen = s
                break
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        avail = screen.availableGeometry()

        too_far_left = current_geo.left() < avail.left() + _MARGIN
        too_far_top = current_geo.top() < avail.top() + _MARGIN
        too_far_right = current_geo.right() > avail.right() - _MARGIN
        too_far_bottom = current_geo.bottom() > avail.bottom() - _MARGIN
        outside = not avail.contains(current_geo)

        if outside or too_far_left or too_far_top or too_far_right or too_far_bottom:
            x = avail.x() + (avail.width() - self.width()) // 2
            y = avail.y() + (avail.height() - self.height()) // 2
            x = max(avail.x() + _MARGIN, min(x, avail.right() - self.width() - _MARGIN))
            y = max(avail.y() + _MARGIN, min(y, avail.bottom() - self.height() - _MARGIN))
            self.move(x, y)

    def summon_pixel(self, source: str = "hotkey") -> None:
        """Instantly restore, raise, and focus Pixel main window upon global hotkey or voice wake."""
        import sys
        from PySide6.QtCore import QThread

        # Ensure execution occurs on the main GUI Qt thread
        if QThread.currentThread() != self.thread():
            QTimer.singleShot(0, lambda: self.summon_pixel(source))
            return

        self.ensure_visible_on_screen()

        # 1. Qt Window State Restoration
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

        # 2. Windows Win32 Direct Foreground Elevation (Bypasses Windows Foreground Lockout)
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                # SW_RESTORE = 9
                user32.ShowWindow(hwnd, 9)

                current_thread = kernel32.GetCurrentThreadId()
                fg_hwnd = user32.GetForegroundWindow()
                fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)

                if fg_thread != 0 and fg_thread != current_thread:
                    user32.AttachThreadInput(fg_thread, current_thread, True)
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                    user32.AttachThreadInput(fg_thread, current_thread, False)
                else:
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
            except Exception:
                pass

        # 3. Focus prompt text editor
        if hasattr(self, "input_bar") and hasattr(self.input_bar, "text_input"):
            self.input_bar.text_input.setFocus(Qt.OtherFocusReason)
            cursor = self.input_bar.text_input.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.input_bar.text_input.setTextCursor(cursor)

        # 4. Living Core Awakening State Pulse
        if hasattr(self, "chat_view") and hasattr(self.chat_view, "set_core_state"):
            self.chat_view.set_core_state(PixelCoreState.AWAKENING)
            QTimer.singleShot(600, lambda: self.chat_view.set_core_state(PixelCoreState.IDLE))

        # 5. Voice acknowledgment if summoned by voice
        if source == "voice" and self.tts_controller and getattr(self.controller.settings, "voice_wake_feedback", True):
            self.tts_controller.speak_text("Ready.", interrupt_current=True)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Conversation", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self.controller.new_conversation)
        file_menu.addAction(new_action)

        file_menu.addSeparator()

        settings_action = QAction("&Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View Menu
        view_menu = menubar.addMenu("&View")

        toggle_diag_action = QAction("&Toggle Diagnostics Drawer", self)
        toggle_diag_action.setShortcut(QKeySequence("Ctrl+D"))
        toggle_diag_action.triggered.connect(self._toggle_diagnostics)
        view_menu.addAction(toggle_diag_action)

        auto_action = QAction("&Automation Center...", self)
        auto_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        auto_action.triggered.connect(self._open_automation)
        view_menu.addAction(auto_action)

        tasks_action = QAction("&Scheduled Tasks...", self)
        tasks_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        tasks_action.triggered.connect(self._open_tasks)
        view_menu.addAction(tasks_action)

        view_menu.addSeparator()

        mem_action = QAction("&Persistent Memory...", self)
        mem_action.triggered.connect(self._open_memories)
        view_menu.addAction(mem_action)

        know_action = QAction("&Knowledge Base (RAG)...", self)
        know_action.triggered.connect(self._open_knowledge)
        view_menu.addAction(know_action)

        view_menu.addSeparator()

        context_action = QAction("&Context Inspector...", self)
        context_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        context_action.triggered.connect(self._open_context_inspector)
        view_menu.addAction(context_action)

        # Speech Menu
        speech_menu = menubar.addMenu("&Speech")
        stop_speech_action = QAction("&Stop Speaking", self)
        stop_speech_action.setShortcut(QKeySequence("Ctrl+."))
        stop_speech_action.triggered.connect(self._on_stop_speech)
        speech_menu.addAction(stop_speech_action)

        # Help Menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Top Header Bar (Subtle living assistant title + quick actions)
        self.header_bar = QWidget()
        self.header_bar.setFixedHeight(42)
        self.header_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_PANEL};
                border-bottom: 1px solid {COLOR_BORDER_SOLID};
            }}
        """)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(12)

        # Sidebar Toggle Button
        self.sidebar_toggle_btn = QPushButton("☰")
        self.sidebar_toggle_btn.setFixedSize(30, 28)
        self.sidebar_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.sidebar_toggle_btn.setToolTip("Toggle Session Sidebar (Ctrl+B)")
        self.sidebar_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLOR_BORDER_SOLID};
                border-radius: 6px;
                color: {COLOR_TEXT_SECONDARY};
                font-size: 14px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                color: {COLOR_ACCENT};
                background-color: rgba(0, 242, 254, 0.08);
            }}
        """)
        self.sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        header_layout.addWidget(self.sidebar_toggle_btn)

        # Assistant Identity & Status Chip
        self.status_pill = QLabel("⚡ PIXEL ● Ready")
        self.status_pill.setStyleSheet(f"""
            color: {COLOR_ACCENT};
            font-weight: 700;
            font-size: 12px;
            letter-spacing: 0.5px;
            padding: 3px 10px;
            border-radius: 12px;
            background-color: rgba(0, 242, 254, 0.08);
            border: 1px solid rgba(0, 242, 254, 0.2);
        """)
        header_layout.addWidget(self.status_pill)

        header_layout.addStretch()

        # New Session Button in Header
        self.header_new_btn = QPushButton("+ Session")
        self.header_new_btn.setObjectName("chipButton")
        self.header_new_btn.setCursor(Qt.PointingHandCursor)
        self.header_new_btn.clicked.connect(self.controller.new_conversation)
        header_layout.addWidget(self.header_new_btn)

        # Diagnostics Drawer Toggle Button
        self.diag_btn = QPushButton("⚙ Diagnostics")
        self.diag_btn.setObjectName("chipButton")
        self.diag_btn.setCursor(Qt.PointingHandCursor)
        self.diag_btn.setToolTip("Toggle Technical Diagnostics Drawer (Ctrl+D)")
        self.diag_btn.clicked.connect(self._toggle_diagnostics)
        header_layout.addWidget(self.diag_btn)

        root_layout.addWidget(self.header_bar)

        # Main horizontal splitter (Sidebar | Chat | Diagnostics Drawer)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(True)

        # 1. Sidebar
        self.sidebar = ConversationSidebar()
        self.splitter.addWidget(self.sidebar)

        # 2. Central Chat Container (ChatView + Floating InputBar)
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.chat_view = ChatView()
        chat_layout.addWidget(self.chat_view)

        self.input_bar = InputBar()
        chat_layout.addWidget(self.input_bar)

        self.splitter.addWidget(chat_container)

        # 3. Diagnostics Drawer (Collapsible)
        self.diagnostics_drawer = DiagnosticsDrawer()
        self.splitter.addWidget(self.diagnostics_drawer)

        # Proportions: 250px sidebar : 800px chat : 0px (drawer starts closed)
        self.splitter.setSizes([250, 900, 0])
        root_layout.addWidget(self.splitter)

        # Minimal Bottom System Status Bar
        self.status_bar = SystemStatusBar()
        root_layout.addWidget(self.status_bar)

    def _toggle_sidebar(self) -> None:
        """Toggle conversation sidebar visibility."""
        is_visible = self.sidebar.isVisible()
        self.sidebar.setVisible(not is_visible)

    def _toggle_diagnostics(self) -> None:
        """Toggle diagnostics drawer visibility."""
        is_open = self.diagnostics_drawer.is_open
        self.diagnostics_drawer.set_open(not is_open)
        if not is_open:
            self.splitter.setSizes([self.splitter.sizes()[0], self.splitter.sizes()[1] - 300, 300])
        else:
            self.splitter.setSizes([self.splitter.sizes()[0], self.splitter.sizes()[1] + 300, 0])

    def _wire_signals(self) -> None:
        # Sidebar to Controller
        self.sidebar.new_chat_clicked.connect(self.controller.new_conversation)
        self.sidebar.conversation_selected.connect(self.controller.switch_conversation)

        # Input to Controller
        self.input_bar.send_submitted.connect(self._on_user_send)
        self.input_bar.cancel_clicked.connect(self.controller.cancel_turn)
        self.input_bar.cancel_clicked.connect(self.chat_view.cancel_assistant_message)
        self.input_bar.attach_image_clicked.connect(self._on_attach_image)
        self.input_bar.capture_screen_clicked.connect(self._on_capture_screen)
        self.input_bar.tier_changed.connect(self._on_tier_changed)

        # Status Bar & Diagnostics to Controller
        self.status_bar.model_changed.connect(self.controller.set_selected_model)
        self.status_bar.refresh_requested.connect(self.controller.check_backend_status)
        self.diagnostics_drawer.model_selected.connect(self.controller.set_selected_model)

        # Controller to UI
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.chunk_received.connect(self._on_chunk_received)
        self.controller.tool_activity_started.connect(self._on_tool_activity_started)
        self.controller.tool_activity_finished.connect(self._on_tool_activity_finished)
        self.controller.turn_metrics_ready.connect(self._on_turn_metrics)
        self.controller.turn_completed.connect(self._on_turn_completed)
        self.controller.turn_error.connect(self._on_turn_error)
        self.controller.conversation_list_updated.connect(
            lambda items: self.sidebar.update_conversations(items, self.controller.agent.conversation.id)
        )
        self.controller.active_conversation_changed.connect(self._on_active_conversation_changed)
        self.controller.backend_status_updated.connect(self._on_backend_status_updated)

        # Confirmation Bridge
        self.controller.gui_confirmation.confirmation_requested.connect(self._show_confirmation_dialog)

        # Voice Input Bridge
        if self.voice_controller:
            self.input_bar.mic_clicked.connect(self.voice_controller.toggle_recording)
            self.voice_controller.voice_state_changed.connect(self._on_voice_state_changed)
            self.voice_controller.recording_duration_tick.connect(
                lambda s: self.input_bar.set_voice_state("recording", s)
            )
            self.voice_controller.transcription_ready.connect(self._on_transcription_ready)
            self.voice_controller.voice_error.connect(self._on_voice_error)

        # Voice Output / TTS Bridge
        if self.tts_controller:
            self.chat_view.speak_requested.connect(self._on_manual_speak_requested)
            self.tts_controller.tts_state_changed.connect(self._on_tts_state_changed)
            self.tts_controller.tts_error.connect(self._on_tts_error)

    def _initial_startup(self) -> None:
        self.controller.check_backend_status()
        self.controller.refresh_conversation_list()
        conv = self.controller.agent.conversation
        if conv and conv.messages:
            self.chat_view.load_messages(conv.messages)

    def _on_attach_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image to Attach",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if file_path:
            try:
                from app.vision.inputs import ImageInputLoader
                loader = ImageInputLoader()
                image_input = loader.load_from_file(file_path)
                self.input_bar.add_image_attachment(image_input)
            except Exception as err:
                QMessageBox.warning(self, "Image Attachment Error", f"Could not load image: {err}")

    def _on_capture_screen(self) -> None:
        try:
            from app.vision.inputs import ImageInputLoader
            loader = ImageInputLoader()
            image_input = loader.capture_screenshot()
            self.input_bar.add_image_attachment(image_input)
        except Exception as err:
            QMessageBox.warning(self, "Screenshot Error", f"Could not capture screenshot: {err}")

    def _on_user_send(self, text: str) -> None:
        if self.tts_controller:
            self.tts_controller.stop_speaking()
        images = self.input_bar.get_attached_images()
        self.input_bar.clear_attachments()
        self.chat_view.add_user_message(text)
        self.chat_view.start_assistant_message()
        self.chat_view.set_core_state(PixelCoreState.THINKING)
        self.status_pill.setText("⚡ PIXEL ● Thinking...")
        self.input_bar.set_running_state(True)
        if images:
            self.controller.send_message(text, images=images)
        else:
            self.controller.send_message(text)

    def _on_chunk_received(self, chunk: str) -> None:
        self.chat_view.append_assistant_chunk(chunk)
        self.chat_view.set_core_state(PixelCoreState.RESPONDING)
        self.status_pill.setText("⚡ PIXEL ● Responding...")

    def _on_tool_activity_started(self, tool_name: str, args: dict[str, Any]) -> None:
        self.chat_view.add_tool_activity(tool_name, args)
        self.chat_view.set_core_state(PixelCoreState.EXECUTING)
        self.status_pill.setText(f"⚡ PIXEL ● Executing {tool_name}...")

    def _on_tool_activity_finished(self, tool_name: str, success: bool, summary: str) -> None:
        self.chat_view.finish_tool_activity(tool_name, success, summary)

    def _on_state_changed(self, state_str: str) -> None:
        state = UIState(state_str)
        is_running = state in (UIState.THINKING, UIState.STREAMING, UIState.EXECUTING_TOOL)
        self.input_bar.set_running_state(is_running)

        if state == UIState.IDLE:
            self.chat_view.set_core_state(PixelCoreState.IDLE)
            self.status_pill.setText("⚡ PIXEL ● Ready")
        elif state == UIState.THINKING:
            self.chat_view.set_core_state(PixelCoreState.THINKING)
            self.status_pill.setText("⚡ PIXEL ● Thinking...")
        elif state == UIState.STREAMING:
            self.chat_view.set_core_state(PixelCoreState.RESPONDING)
            self.status_pill.setText("⚡ PIXEL ● Responding...")
        elif state == UIState.EXECUTING_TOOL:
            self.chat_view.set_core_state(PixelCoreState.EXECUTING)
            self.status_pill.setText("⚡ PIXEL ● Executing...")

    def _on_tier_changed(self, tier: str) -> None:
        self.controller.set_selected_model(tier)
        self.status_bar.set_tier_badge(tier)

    def _on_turn_metrics(self, metrics: Any) -> None:
        self.chat_view.set_current_metrics(metrics)
        self.diagnostics_drawer.update_turn_metrics(metrics)
        self.status_bar.set_performance_metric(
            model_name=getattr(metrics, "model_name", ""),
            latency_seconds=getattr(metrics, "total_time", 0.0),
            tok_per_sec=getattr(metrics, "tokens_per_second", 0.0),
        )

    def _on_backend_status_updated(self, status: Any) -> None:
        self.status_bar.update_status(status)
        self.diagnostics_drawer.update_backend_status(status)
        self.sidebar.update_resource_meters(
            cpu_percent=getattr(status, "cpu_percent", 0.0),
            ram_percent=getattr(status, "ram_percent", 0.0),
        )

    def _on_turn_completed(self, full_response: str) -> None:
        self.input_bar.set_running_state(False)
        self.chat_view.set_core_state(PixelCoreState.SUCCESS)
        self.status_pill.setText("⚡ PIXEL ● Ready")
        QTimer.singleShot(1500, lambda: self.chat_view.set_core_state(PixelCoreState.IDLE))

        if not full_response or not full_response.strip():
            if self.chat_view._current_assistant_bubble and not self.chat_view._current_assistant_bubble.get_content().strip():
                diag = getattr(self.chat_view, "_latest_metrics", None)
                model_info = getattr(diag, "model_name", "local model")
                tier_info = getattr(diag, "tier", "FAST_MODEL")
                self.chat_view._current_assistant_bubble.set_content(
                    f"*(No response returned by {model_info} [{tier_info}]. Verify that Ollama is active.)*"
                )

        if self.tts_controller and full_response and full_response.strip():
            self.tts_controller.handle_turn_completed(full_response)

    def _on_turn_error(self, error_msg: str) -> None:
        self.input_bar.set_running_state(False)
        self.chat_view.mark_assistant_error(error_msg)
        self.chat_view.set_core_state(PixelCoreState.ERROR)
        self.status_pill.setText("⚠ PIXEL ● Error")
        QTimer.singleShot(3000, lambda: self.chat_view.set_core_state(PixelCoreState.IDLE))

    def _on_active_conversation_changed(self, cid: str, title: str, messages: list) -> None:
        if self.tts_controller:
            self.tts_controller.stop_speaking()
        self.sidebar.set_active_id(cid)
        self.chat_view.load_messages(messages)

    def _show_confirmation_dialog(
        self,
        context: Any,
        decision: Any,
        event: threading.Event,
        result_holder: list[bool],
    ) -> None:
        try:
            dialog = ConfirmationDialog(context=context, decision=decision, parent=self)
            dialog.exec()
            result_holder[0] = dialog.is_allowed()
        except Exception:
            result_holder[0] = False
        finally:
            event.set()

    def _open_automation(self) -> None:
        if self.automation_controller:
            dlg = AutomationDialog(
                automation_controller=self.automation_controller,
                task_controller=self.task_controller,
                parent=self,
            )
            dlg.exec()
        else:
            QMessageBox.information(self, "Notice", "Automation subsystem is not active.")

    def _open_tasks(self) -> None:
        if self.task_controller:
            dlg = TasksDialog(task_controller=self.task_controller, parent=self)
            dlg.exec()
        else:
            QMessageBox.information(self, "Notice", "Task management subsystem is not active.")

    def _open_memories(self) -> None:
        dlg = MemoryDialog(memory_manager=self.controller.memory_manager, parent=self)
        dlg.exec()

    def _open_knowledge(self) -> None:
        dlg = KnowledgeDialog(knowledge_manager=self.controller.knowledge_manager, parent=self)
        dlg.exec()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(settings=self.controller.settings, parent=self)
        dlg.exec()

    def _open_context_inspector(self) -> None:
        from app.ui.widgets.context_dialog import ContextInspectorDialog
        diag = None
        if hasattr(self.controller, "context_manager") and self.controller.context_manager:
            diag = self.controller.context_manager.get_last_diagnostics()
        dlg = ContextInspectorDialog(diagnostics=diag, parent=self)
        dlg.exec()

    def _show_about(self) -> None:
        cfg = self.controller.settings
        QMessageBox.about(
            self,
            f"About {cfg.app_name}",
            f"<b>{cfg.app_name} (v{cfg.version} • build: {cfg.build_commit})</b><br><br>"
            "A living, cinematic, fully local AI personal assistant powered by Ollama.<br>"
            "69+ registered tools across Filesystem, System, Apps, Terminal, Memory, RAG, and Browser.<br><br>"
            "Local Voice Input (STT) and Voice Output (TTS) with 100% offline privacy.",
        )

    def _on_voice_state_changed(self, state_str: str) -> None:
        self.input_bar.set_voice_state(state_str)
        self.status_bar.set_voice_state(state_str)
        if state_str == "recording":
            self.chat_view.set_core_state(PixelCoreState.LISTENING)
            self.status_pill.setText("🎤 PIXEL ● Listening...")
        elif state_str == "transcribing":
            self.chat_view.set_core_state(PixelCoreState.THINKING)
            self.status_pill.setText("⚡ PIXEL ● Transcribing...")
        else:
            self.chat_view.set_core_state(PixelCoreState.IDLE)
            self.status_pill.setText("⚡ PIXEL ● Ready")

    def _on_transcription_ready(self, text: str) -> None:
        self.input_bar.set_text(text)

    def _on_voice_error(self, err_msg: str) -> None:
        self.input_bar.set_voice_state("idle")
        self.status_bar.set_voice_state("idle")
        self.chat_view.set_core_state(PixelCoreState.ERROR)
        QMessageBox.warning(self, "Voice Input Notice", err_msg)

    def _on_manual_speak_requested(self, text: str) -> None:
        if self.tts_controller:
            self.tts_controller.speak_text(text, interrupt_current=True)

    def _on_tts_state_changed(self, state_str: str) -> None:
        self.status_bar.set_tts_state(state_str)
        if state_str == "speaking":
            self.chat_view.set_core_state(PixelCoreState.RESPONDING)
            self.status_pill.setText("🔊 PIXEL ● Speaking...")
        elif state_str == "synthesizing":
            self.chat_view.set_core_state(PixelCoreState.THINKING)
        else:
            if not self.input_bar.send_btn.isHidden():
                self.chat_view.set_core_state(PixelCoreState.IDLE)
                self.status_pill.setText("⚡ PIXEL ● Ready")

    def _on_tts_error(self, err_msg: str) -> None:
        self.status_bar.set_tts_state("idle")
        QMessageBox.warning(self, "Speech Output Notice", err_msg)

    def _on_stop_speech(self) -> None:
        if self.tts_controller:
            self.tts_controller.stop_speaking()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.status_timer.isActive():
            self.status_timer.start(5000)

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        if self.controller.settings.minimize_to_tray:
            event.ignore()
            self.hide()
            return

        if self.voice_controller:
            try:
                self.voice_controller.cancel_recording()
            except Exception:
                pass
        if self.tts_controller:
            try:
                self.tts_controller.stop_speaking()
            except Exception:
                pass
        self.controller.shutdown()
        event.accept()


