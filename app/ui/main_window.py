"""Main application window coordinating UI layout, menus, controllers, and dialogs."""

import threading
from typing import Any, Optional
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.controller import AssistantController
from app.ui.models import UIState
from app.ui.theme import APPLICATION_STYLESHEET
from app.ui.widgets.automation_dialog import AutomationDialog

from app.ui.widgets.chat_view import ChatView
from app.ui.widgets.confirmation_dialog import ConfirmationDialog
from app.ui.widgets.input_bar import InputBar
from app.ui.widgets.knowledge_dialog import KnowledgeDialog
from app.ui.widgets.memory_dialog import MemoryDialog
from app.ui.widgets.settings_dialog import SettingsDialog
from app.ui.widgets.sidebar import ConversationSidebar
from app.ui.widgets.status_bar import SystemStatusBar
from app.ui.widgets.tasks_dialog import TasksDialog


class MainWindow(QMainWindow):
    """Primary desktop application window for the Local AI Personal Assistant."""

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
        self.resize(1100, 750)
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
        """Validate window geometry against all displays and center if outside or too close to edge.

        A margin of 50 px is enforced on all sides so that the title-bar and
        taskbar region do not hide the window even when coordinates look valid.
        """
        from PySide6.QtGui import QGuiApplication

        _MARGIN = 50  # px safety margin from screen edge
        current_geo = self.frameGeometry()

        # Try to find the screen that currently contains the window centre
        centre = current_geo.center()
        screen = None
        for s in QGuiApplication.screens():
            if s.availableGeometry().contains(centre):
                screen = s
                break
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return  # no display detected — skip

        avail = screen.availableGeometry()

        # Determine if the window is within safe bounds
        too_far_left   = current_geo.left()   < avail.left()   + _MARGIN
        too_far_top    = current_geo.top()    < avail.top()    + _MARGIN
        too_far_right  = current_geo.right()  > avail.right()  - _MARGIN
        too_far_bottom = current_geo.bottom() > avail.bottom() - _MARGIN
        outside = not avail.contains(current_geo)

        if outside or too_far_left or too_far_top or too_far_right or too_far_bottom:
            x = avail.x() + (avail.width()  - self.width())  // 2
            y = avail.y() + (avail.height() - self.height()) // 2
            # Clamp to margins
            x = max(avail.x() + _MARGIN, min(x, avail.right()  - self.width()  - _MARGIN))
            y = max(avail.y() + _MARGIN, min(y, avail.bottom() - self.height() - _MARGIN))
            self.move(x, y)

    def summon_pixel(self, source: str = "hotkey") -> None:
        """Instantly restore, raise, and focus Pixel main window upon global hotkey or voice wake."""
        self.ensure_visible_on_screen()
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

        # Focus input bar text editor immediately
        if hasattr(self, "input_bar") and hasattr(self.input_bar, "text_input"):
            self.input_bar.text_input.setFocus()
            cursor = self.input_bar.text_input.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.input_bar.text_input.setTextCursor(cursor)

        # If summoned by voice and TTS feedback is active, acknowledge with quick local TTS
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

        # Speech Menu (Phase 13)
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

        # Main horizontal splitter (Sidebar | Chat)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Sidebar
        self.sidebar = ConversationSidebar()
        self.splitter.addWidget(self.sidebar)

        # Chat Area Container (ChatView + InputBar)
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.chat_view = ChatView()
        chat_layout.addWidget(self.chat_view)

        self.input_bar = InputBar()
        chat_layout.addWidget(self.input_bar)

        self.splitter.addWidget(chat_container)

        # Set initial splitter proportions (260px sidebar : remaining chat)
        self.splitter.setSizes([260, 840])
        root_layout.addWidget(self.splitter)

        # System Status Bar at the bottom
        self.status_bar = SystemStatusBar()
        root_layout.addWidget(self.status_bar)

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

        # Status Bar to Controller
        self.status_bar.model_changed.connect(self.controller.set_selected_model)
        self.status_bar.refresh_requested.connect(self.controller.check_backend_status)

        # Controller to UI
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.chunk_received.connect(self.chat_view.append_assistant_chunk)
        self.controller.tool_activity_started.connect(self.chat_view.add_tool_activity)
        self.controller.tool_activity_finished.connect(self.chat_view.finish_tool_activity)
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

        # Voice Input Bridge (Phase 12)
        if self.voice_controller:
            self.input_bar.mic_clicked.connect(self.voice_controller.toggle_recording)
            self.voice_controller.voice_state_changed.connect(self._on_voice_state_changed)
            self.voice_controller.recording_duration_tick.connect(
                lambda s: self.input_bar.set_voice_state("recording", s)
            )
            self.voice_controller.transcription_ready.connect(self._on_transcription_ready)
            self.voice_controller.voice_error.connect(self._on_voice_error)

        # Voice Output / TTS Bridge (Phase 13)
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
        # Stop any currently playing speech when user sends a new message
        if self.tts_controller:
            self.tts_controller.stop_speaking()
        images = self.input_bar.get_attached_images()
        self.input_bar.clear_attachments()
        self.chat_view.add_user_message(text)
        self.chat_view.start_assistant_message()
        self.input_bar.set_running_state(True)
        if images:
            self.controller.send_message(text, images=images)
        else:
            self.controller.send_message(text)

    def _on_state_changed(self, state_str: str) -> None:
        state = UIState(state_str)
        is_running = state in (UIState.THINKING, UIState.STREAMING, UIState.EXECUTING_TOOL)
        self.input_bar.set_running_state(is_running)

    def _on_tier_changed(self, tier: str) -> None:
        self.controller.set_selected_model(tier)
        self.status_bar.set_tier_badge(tier)

    def _on_turn_metrics(self, metrics: Any) -> None:
        self.chat_view.set_current_metrics(metrics)
        self.status_bar.set_performance_metric(
            model_name=getattr(metrics, "model_name", ""),
            latency_seconds=getattr(metrics, "total_time", 0.0),
            tok_per_sec=getattr(metrics, "tokens_per_second", 0.0),
        )

    def _on_backend_status_updated(self, status: Any) -> None:
        self.status_bar.update_status(status)
        self.sidebar.update_resource_meters(
            cpu_percent=getattr(status, "cpu_percent", 0.0),
            ram_percent=getattr(status, "ram_percent", 0.0),
        )

    def _on_turn_completed(self, full_response: str) -> None:
        self.input_bar.set_running_state(False)
        if not full_response or not full_response.strip():
            if self.chat_view._current_assistant_bubble and not self.chat_view._current_assistant_bubble.get_content().strip():
                self.chat_view._current_assistant_bubble.set_content("*(No response produced)*")
        # Handle auto-speak if configured
        if self.tts_controller and full_response and full_response.strip():
            self.tts_controller.handle_turn_completed(full_response)

    def _on_turn_error(self, error_msg: str) -> None:
        self.input_bar.set_running_state(False)
        self.chat_view.mark_assistant_error(error_msg)

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
        """Display the modal confirmation dialog on the main UI thread."""
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
            f"<b>{cfg.app_name} (v{cfg.version})</b><br><br>"
            "A secure, fully local AI personal assistant powered by Ollama.<br>"
            "49 registered tools across Filesystem, System, Apps, Terminal, Memory, RAG, and Browser.<br><br>"
            "Local Voice Input (STT) and Voice Output (TTS) with 100% offline privacy.",
        )

    def _on_voice_state_changed(self, state_str: str) -> None:
        """Reflect voice recording and transcribing states across input and status bar."""
        self.input_bar.set_voice_state(state_str)
        self.status_bar.set_voice_state(state_str)

    def _on_transcription_ready(self, text: str) -> None:
        """Place transcribed speech into input field for user review and editing."""
        self.input_bar.set_text(text)

    def _on_voice_error(self, err_msg: str) -> None:
        """Display friendly notice when voice recording or transcription fails."""
        self.input_bar.set_voice_state("idle")
        self.status_bar.set_voice_state("idle")
        QMessageBox.warning(self, "Voice Input Notice", err_msg)

    def _on_manual_speak_requested(self, text: str) -> None:
        """Handle manual speak button clicked on a message bubble."""
        if self.tts_controller:
            self.tts_controller.speak_text(text, interrupt_current=True)

    def _on_tts_state_changed(self, state_str: str) -> None:
        """Update TTS status indicator."""
        self.status_bar.set_tts_state(state_str)

    def _on_tts_error(self, err_msg: str) -> None:
        """Display notice on TTS playback error."""
        self.status_bar.set_tts_state("idle")
        QMessageBox.warning(self, "Speech Output Notice", err_msg)

    def _on_stop_speech(self) -> None:
        """Halt active speech and clear queue."""
        if self.tts_controller:
            self.tts_controller.stop_speaking()

    def showEvent(self, event) -> None:
        """Restart status timer when window is shown."""
        super().showEvent(event)
        if not self.status_timer.isActive():
            self.status_timer.start(5000)

    def closeEvent(self, event) -> None:
        """Handle window close event: minimize to system tray if configured, or exit cleanly."""
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


