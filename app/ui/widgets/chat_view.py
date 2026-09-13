"""Scrollable conversation history view managing Pixel message bubbles, tool activities, and AI core animation."""

from typing import Any, Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.agent.conversation import Message
from app.ui.models import MessageRole, TurnMetrics
from app.ui.widgets.message_bubble import MessageBubble
from app.ui.widgets.pixel_core import PixelCoreState, PixelCoreWidget
from app.ui.widgets.tool_activity import ToolActivityWidget


class ChatView(QScrollArea):
    """Scrollable container rendering conversation messages, intermediate tool badges, and Pixel AI Core."""

    speak_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(20, 16, 20, 16)
        self.container_layout.setSpacing(12)

        # AI Core Visual Header (Living presence at top of conversation)
        core_box = QWidget()
        core_layout = QHBoxLayout(core_box)
        core_layout.setContentsMargins(0, 4, 0, 8)
        core_layout.addStretch()
        self.core_widget = PixelCoreWidget(state=PixelCoreState.IDLE, size=88)
        core_layout.addWidget(self.core_widget)
        core_layout.addStretch()
        self.container_layout.addWidget(core_box)

        # Bottom stretch to keep messages pushed downwards cleanly
        self.container_layout.addStretch()

        self.setWidget(self.container)
        self._current_assistant_bubble: Optional[MessageBubble] = None
        self._active_tools: dict[str, ToolActivityWidget] = {}

    def set_core_state(self, state: PixelCoreState) -> None:
        """Update the visual animation state of the Pixel AI Core."""
        if hasattr(self, "core_widget") and self.core_widget:
            self.core_widget.set_state(state)

    def scroll_to_bottom(self) -> None:
        """Ensure latest messages are visible with smooth response."""
        QTimer.singleShot(10, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

    def add_user_message(self, text: str) -> MessageBubble:
        """Add user message bubble to view."""
        bubble = MessageBubble(role=MessageRole.USER, initial_content=text)
        idx = max(1, self.container_layout.count() - 1)
        self.container_layout.insertWidget(idx, bubble)
        self.scroll_to_bottom()
        return bubble

    def start_assistant_message(self, status_text: str = "PIXEL THINKING // Analyzing intent...") -> MessageBubble:
        """Create a new streaming assistant bubble showing a thinking placeholder."""
        bubble = MessageBubble(role=MessageRole.ASSISTANT, initial_content="")
        bubble.set_thinking(status_text)
        bubble.speak_clicked.connect(self.speak_requested.emit)
        idx = max(1, self.container_layout.count() - 1)
        self.container_layout.insertWidget(idx, bubble)
        self._current_assistant_bubble = bubble
        self.scroll_to_bottom()
        return bubble

    def update_thinking_stage(self, stage_text: str) -> None:
        """Update the active thinking indicator text with fine-grained stage information."""
        if self._current_assistant_bubble and self._current_assistant_bubble._is_thinking:
            self._current_assistant_bubble.set_thinking(stage_text)

    def set_current_metrics(self, metrics: TurnMetrics) -> None:
        """Apply performance and generation telemetry to the active assistant bubble."""
        if self._current_assistant_bubble:
            self._current_assistant_bubble.set_metrics(metrics)
            self.scroll_to_bottom()

    def mark_assistant_error(self, error_msg: str) -> None:
        """Update current assistant bubble to show error state."""
        if self._current_assistant_bubble:
            self._current_assistant_bubble.set_error(error_msg)
            self.scroll_to_bottom()
        else:
            bubble = self.start_assistant_message()
            bubble.set_error(error_msg)

    def cancel_assistant_message(self) -> None:
        """Handle turn cancellation cleanly."""
        if self._current_assistant_bubble:
            if not self._current_assistant_bubble.get_content():
                self._current_assistant_bubble.set_content("*(Generation stopped by user)*")
            self.scroll_to_bottom()

    def append_assistant_chunk(self, chunk: str) -> None:
        """Append streamed token chunk to active assistant bubble."""
        if not self._current_assistant_bubble:
            self.start_assistant_message()
        self._current_assistant_bubble.append_chunk(chunk)
        self.scroll_to_bottom()

    def add_tool_activity(self, tool_name: str, args: dict[str, Any]) -> ToolActivityWidget:
        """Add an in-progress tool activity card."""
        widget = ToolActivityWidget(tool_name=tool_name, initial_args=args)
        idx = max(1, self.container_layout.count() - 1)
        self.container_layout.insertWidget(idx, widget)
        self._active_tools[tool_name] = widget
        self.scroll_to_bottom()
        return widget

    def finish_tool_activity(self, tool_name: str, success: bool, summary: str) -> None:
        """Mark tool activity card as finished."""
        widget = self._active_tools.get(tool_name)
        if widget:
            widget.set_finished(success, summary)
            self.scroll_to_bottom()

    def clear(self) -> None:
        """Clear all conversation messages from the view, preserving the core header."""
        while self.container_layout.count() > 2:  # index 0 is core_box, last is stretch
            item = self.container_layout.takeAt(1)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._current_assistant_bubble = None
        self._active_tools.clear()

    def load_messages(self, messages: list[Message]) -> None:
        """Populate view from persistent conversation messages."""
        self.clear()
        for msg in messages:
            if msg.role == "user":
                self.add_user_message(msg.content)
            elif msg.role == "assistant" and msg.content:
                bubble = MessageBubble(role=MessageRole.ASSISTANT, initial_content=msg.content)
                bubble.speak_clicked.connect(self.speak_requested.emit)
                idx = max(1, self.container_layout.count() - 1)
                self.container_layout.insertWidget(idx, bubble)
        self.scroll_to_bottom()
