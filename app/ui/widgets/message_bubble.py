"""Message bubble widget with Jarvis-class styling, telemetry chips, copy actions, and TTS."""

from datetime import datetime, timezone
import html
import re
from typing import Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ui.models import MessageRole, TurnMetrics
from app.ui.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_BG_DARK,
    COLOR_BG_INPUT,
    COLOR_BG_PANEL,
    COLOR_BG_SURFACE,
    COLOR_BORDER,
    COLOR_BORDER_FOCUS,
    COLOR_DANGER,
    COLOR_PURPLE,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_WHITE,
    COLOR_WARNING,
)


def _format_markdown_to_html(text: str) -> str:
    """Lightweight deterministic markdown to HTML converter for Jarvis chat bubbles."""
    escaped = html.escape(text)

    # Code blocks: ```language ... ```
    escaped = re.sub(
        r"```(\w*)\n(.*?)```",
        r'<div style="margin: 8px 0; border: 1px solid #2b324c; border-radius: 6px; overflow: hidden;">'
        r'<div style="background-color: #141724; padding: 4px 10px; font-family: Consolas, monospace; font-size: 10px; color: #00f2fe; border-bottom: 1px solid #2b324c; font-weight: bold;">\1 CODE BLOCK</div>'
        r'<pre style="background-color: #0a0c14; padding: 10px 12px; margin: 0; font-family: Consolas, monospace; font-size: 12px; color: #e2e8f0; line-height: 1.4;"><code>\2</code></pre>'
        r'</div>',
        escaped,
        flags=re.DOTALL,
    )
    # Inline code: `code`
    escaped = re.sub(
        r"`([^`]+)`",
        r'<code style="background-color: #131728; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; color: #00f2fe; border: 1px solid #2b324c;">\1</code>',
        escaped,
    )
    # Bold: **bold**
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b style='color: #ffffff;'>\1</b>", escaped)
    # Italics: *italic*
    escaped = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", escaped)
    # Lists: - item
    escaped = re.sub(r"^[ \t]*-[ \t]+(.*)$", r"• \1", escaped, flags=re.MULTILINE)

    # Paragraphs
    paragraphs = escaped.split("\n\n")
    html_paragraphs = []
    for p in paragraphs:
        if not p.startswith("<div"):
            p = p.replace("\n", "<br>")
        html_paragraphs.append(p)

    return "<p style='margin: 0; line-height: 1.5;'>" + "</p><p style='margin: 8px 0 0 0; line-height: 1.5;'>".join(html_paragraphs) + "</p>"


class MessageBubble(QWidget):
    """Chat message card with HUD identity badges, latency telemetry chip, copy button, and TTS triggers."""

    speak_clicked = Signal(str)

    def __init__(
        self,
        role: MessageRole,
        initial_content: str = "",
        timestamp: Optional[datetime] = None,
        metrics: Optional[TurnMetrics] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        self._raw_content = initial_content
        self._metrics = metrics
        self._is_thinking = (role == MessageRole.ASSISTANT and not initial_content)
        self.timestamp = timestamp or datetime.now(timezone.utc)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(4)

        # Header Row: Role Badge | Time | Actions (Copy, TTS)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(8)

        # Futuristic Role Badge
        if role == MessageRole.USER:
            role_text = "OPERATOR // YOU"
            role_style = "color: #00f2fe; font-size: 10px; font-weight: 800; letter-spacing: 0.8px; font-family: Consolas, monospace;"
        elif role == MessageRole.ASSISTANT:
            role_text = "JARVIS // ASSISTANT"
            role_style = "color: #a855f7; font-size: 10px; font-weight: 800; letter-spacing: 0.8px; font-family: Consolas, monospace;"
        else:
            role_text = "SYSTEM // CORE"
            role_style = "color: #f59e0b; font-size: 10px; font-weight: 800; letter-spacing: 0.8px; font-family: Consolas, monospace;"

        role_label = QLabel(role_text)
        role_label.setStyleSheet(role_style)
        header_layout.addWidget(role_label)

        time_str = self.timestamp.strftime("%H:%M")
        time_label = QLabel(time_str)
        time_label.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_MUTED}; font-family: Consolas, monospace;")
        header_layout.addWidget(time_label)

        header_layout.addStretch()

        # Copy button (available for all messages)
        self.copy_btn = QPushButton("📋")
        self.copy_btn.setFixedSize(22, 20)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip("Copy message text to clipboard")
        self.copy_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                font-size: 11px;
                color: {COLOR_TEXT_MUTED};
            }}
            QPushButton:hover {{
                color: {COLOR_ACCENT};
            }}
        """)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        header_layout.addWidget(self.copy_btn)

        # Speak button for assistant messages
        if role == MessageRole.ASSISTANT:
            self.speak_btn = QPushButton("🔊")
            self.speak_btn.setFixedSize(22, 20)
            self.speak_btn.setCursor(Qt.PointingHandCursor)
            self.speak_btn.setToolTip("Speak response (Local TTS)")
            self.speak_btn.setStyleSheet(f"""
                QPushButton {{
                    border: none;
                    background: transparent;
                    font-size: 11px;
                    color: {COLOR_TEXT_MUTED};
                }}
                QPushButton:hover {{
                    color: #4facfe;
                }}
            """)
            self.speak_btn.clicked.connect(lambda: self.speak_clicked.emit(self._raw_content))
            header_layout.addWidget(self.speak_btn)

        main_layout.addLayout(header_layout)

        # Content Text Browser
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        if role == MessageRole.USER:
            bg_color = "#181d2f"
            border_style = "border: 1px solid #2e385c; border-left: 3px solid #00f2fe;"
        elif role == MessageRole.ASSISTANT:
            bg_color = "#131624"
            border_style = "border: 1px solid #232840; border-left: 3px solid #a855f7;"
        else:
            bg_color = "#181520"
            border_style = "border: 1px solid #382c1e; border-left: 3px solid #f59e0b;"

        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {bg_color};
                {border_style}
                border-radius: 8px;
                padding: 10px 14px;
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        # Telemetry Footer (for assistant messages)
        self.telemetry_label = QLabel()
        self.telemetry_label.setStyleSheet(f"""
            font-size: 10px;
            font-family: Consolas, monospace;
            color: {COLOR_TEXT_MUTED};
            padding-left: 6px;
        """)
        self.telemetry_label.setVisible(False)

        self._update_rendered_content()
        main_layout.addWidget(self.browser)
        main_layout.addWidget(self.telemetry_label)

        if metrics:
            self.set_metrics(metrics)

    def _copy_to_clipboard(self) -> None:
        """Copy raw message text to clipboard with visual confirmation."""
        if self._raw_content:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(self._raw_content)
                self.copy_btn.setText("✓")
                QTimer.singleShot(1500, lambda: self.copy_btn.setText("📋"))

    def set_thinking(self, status_text: str = "JARVIS PROCESSING // Analyzing intent...") -> None:
        """Display an animated HUD thinking indicator."""
        self._is_thinking = True
        html_content = (
            f'<div style="color: #64748b; font-family: Consolas, monospace; font-size: 11px;">'
            f'<span style="color: #00f2fe; font-weight: bold;">◌ </span>'
            f'<span>{html.escape(status_text)}</span>'
            f'</div>'
        )
        self.browser.setHtml(html_content)
        self.browser.setFixedHeight(46)
        if hasattr(self, "telemetry_label"):
            self.telemetry_label.setVisible(False)

    def append_chunk(self, chunk: str) -> None:
        """Append streaming tokens to the message and update display."""
        self._is_thinking = False
        self._raw_content += chunk
        self._update_rendered_content()

    def set_content(self, text: str) -> None:
        """Replace message content completely."""
        self._is_thinking = False
        self._raw_content = text
        self._update_rendered_content()

    def set_metrics(self, metrics: TurnMetrics) -> None:
        """Render latency and model generation telemetry chip."""
        self._metrics = metrics
        parts = []
        if metrics.tokens_per_second > 0:
            parts.append(f"⚡ {metrics.tokens_per_second:.1f} tok/s")
        if metrics.ttft is not None:
            parts.append(f"{metrics.ttft:.2f}s TTFT")
        if metrics.total_time > 0:
            parts.append(f"{metrics.total_time:.2f}s total")
        if metrics.model_name:
            role_tag = f" [{metrics.role.upper()}]" if metrics.role else ""
            parts.append(f"{metrics.model_name}{role_tag}")

        if parts:
            self.telemetry_label.setText(" • ".join(parts))
            self.telemetry_label.setVisible(True)

    def set_error(self, error_msg: str) -> None:
        """Display a formatted error notification inside the assistant bubble."""
        self._is_thinking = False
        self._raw_content = f"⚠ **Unable to generate a response.**\n\n*Reason:* {error_msg}"
        html_content = (
            f'<div style="color: #f43f5e; background-color: rgba(244, 63, 94, 0.08); '
            f'border-left: 3px solid #f43f5e; padding: 8px 12px; border-radius: 4px; font-family: Consolas, monospace;">'
            f'<b style="color: #ffffff;">⚠ Unable to generate a response.</b><br><br>'
            f'<span style="color: #94a3b8; font-size: 11px;">Reason: {html.escape(error_msg)}</span>'
            f'</div>'
        )
        self.browser.setHtml(html_content)
        doc_height = int(self.browser.document().size().height()) + 28
        self.browser.setFixedHeight(max(55, doc_height))

    def get_content(self) -> str:
        return self._raw_content

    def _update_rendered_content(self) -> None:
        if self._is_thinking:
            self.set_thinking()
            return
        formatted = _format_markdown_to_html(self._raw_content)
        self.browser.setHtml(formatted)
        doc_height = int(self.browser.document().size().height()) + 28
        self.browser.setFixedHeight(max(42, doc_height))
