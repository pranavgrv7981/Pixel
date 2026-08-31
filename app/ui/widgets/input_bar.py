"""Input bar widget providing multiline prompt editing, send, cancellation, voice capture, and image attachment controls."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QKeyEvent, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

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
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_WHITE,
    COLOR_WARNING,
)
from app.vision.models import ImageInput


class PromptTextEdit(QTextEdit):
    """Text edit capturing Enter to send and Shift+Enter for newline."""

    return_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                # Shift+Enter: normal newline
                super().keyPressEvent(event)
            else:
                # Enter: emit send signal
                event.accept()
                self.return_pressed.emit()
        else:
            super().keyPressEvent(event)


class ImageThumbnailWidget(QWidget):
    """Small thumbnail widget displaying an attached image with filename, dimensions, and remove button."""

    remove_requested = Signal(str)

    def __init__(self, image_input: ImageInput, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.image_input = image_input

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Image preview thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(32, 32)
        self.thumb_label.setScaledContents(True)

        if image_input.path:
            pix = QPixmap(image_input.path)
            if not pix.isNull():
                self.thumb_label.setPixmap(pix.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.thumb_label.setText("🖼")
        else:
            self.thumb_label.setText("🖼")

        layout.addWidget(self.thumb_label)

        # Name and dimension metadata
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        name_lbl = QLabel(image_input.filename)
        name_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 11px; font-weight: bold; font-family: Consolas, monospace;")
        info_layout.addWidget(name_lbl)

        dim_lbl = QLabel(f"{image_input.dimensions_str} • {image_input.size_kb} KB")
        dim_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-family: Consolas, monospace;")
        info_layout.addWidget(dim_lbl)

        layout.addLayout(info_layout)

        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COLOR_TEXT_MUTED};
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COLOR_DANGER};
            }}
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.image_input.id))
        layout.addWidget(remove_btn)


class InputBar(QWidget):
    """Command capsule input bar with quick action chips, multiline prompt, voice STT, and attachment controls."""

    send_submitted = Signal(str)
    cancel_clicked = Signal()
    mic_clicked = Signal()
    attach_image_clicked = Signal()
    capture_screen_clicked = Signal()
    tier_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._attached_images: list[ImageInput] = []

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_PANEL};
                border-top: 1px solid {COLOR_BORDER};
            }}
        """)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(18, 10, 18, 14)
        main_vbox.setSpacing(8)

        # 1. Quick Actions & Mode Bar (Top Chip Strip)
        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(8)

        # Tier Selector Chip
        self.tier_chip = QPushButton("⚡ Mode: Auto")
        self.tier_chip.setObjectName("chipButton")
        self.tier_chip.setToolTip("Execution Strategy: Auto-selects Fast, Standard, or Heavy model tier")
        self.tier_chip.setCursor(Qt.PointingHandCursor)
        self.tier_chip.clicked.connect(self._cycle_tier)
        chips_row.addWidget(self.tier_chip)
        self._tier_modes = ["auto", "fast", "standard", "heavy"]
        self._current_tier_idx = 0

        # Action: Voice
        self.mic_chip = QPushButton("🎤")
        self.mic_chip.setObjectName("chipButton")
        self.mic_chip.setToolTip("Record speech locally via Faster-Whisper")
        self.mic_chip.setCursor(Qt.PointingHandCursor)
        self.mic_chip.clicked.connect(self.mic_clicked.emit)
        chips_row.addWidget(self.mic_chip)

        # Action: Screen Capture
        self.screen_chip = QPushButton("📷")
        self.screen_chip.setObjectName("chipButton")
        self.screen_chip.setToolTip("Capture desktop window screenshot")
        self.screen_chip.setCursor(Qt.PointingHandCursor)
        self.screen_chip.clicked.connect(self.capture_screen_clicked.emit)
        chips_row.addWidget(self.screen_chip)

        # Action: Attach Image
        self.attach_chip = QPushButton("📎")
        self.attach_chip.setObjectName("chipButton")
        self.attach_chip.setToolTip("Attach an image file for vision analysis")
        self.attach_chip.setCursor(Qt.PointingHandCursor)
        self.attach_chip.clicked.connect(self.attach_image_clicked.emit)
        chips_row.addWidget(self.attach_chip)

        # Backward compatibility aliases for existing fixtures & tests
        self.mic_btn = self.mic_chip
        self.screen_btn = self.screen_chip
        self.attach_btn = self.attach_chip

        chips_row.addStretch()

        # Keyboard Legend
        hint_label = QLabel("[Enter ↵] Send • [Shift+↵] Newline")
        hint_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-family: Consolas, monospace;")
        chips_row.addWidget(hint_label)

        main_vbox.addLayout(chips_row)

        # 2. Attachment Bar (hidden when empty)
        self.attachment_bar = QWidget()
        self.attachment_layout = QHBoxLayout(self.attachment_bar)
        self.attachment_layout.setContentsMargins(0, 0, 0, 0)
        self.attachment_layout.setSpacing(8)
        self.attachment_layout.addStretch()
        self.attachment_bar.setVisible(False)
        main_vbox.addWidget(self.attachment_bar)

        # 3. Main Prompt Capsule (Text Input + Send/Stop Button)
        input_container = QWidget()
        input_container.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 10px;
            }}
        """)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(10, 6, 10, 6)
        input_layout.setSpacing(10)

        # Prompt input text box
        self.text_input = PromptTextEdit()
        self.text_input.setPlaceholderText("Ask Jarvis anything or execute a command...")
        self.text_input.setFixedHeight(48)
        self.text_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                padding: 4px 6px;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
            }}
        """)
        self.text_input.return_pressed.connect(self._handle_send)
        input_layout.addWidget(self.text_input)

        # Send Button (Primary Gradient)
        self.send_btn = QPushButton("Send ↵")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setFixedSize(76, 36)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._handle_send)
        input_layout.addWidget(self.send_btn)

        # Stop / Cancel Button (initially hidden)
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setFixedSize(76, 36)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.cancel_clicked.emit)
        self.stop_btn.setVisible(False)
        input_layout.addWidget(self.stop_btn)

        main_vbox.addWidget(input_container)

    def _cycle_tier(self) -> None:
        """Cycle through Auto, Fast, Standard, and Heavy execution tiers."""
        self._current_tier_idx = (self._current_tier_idx + 1) % len(self._tier_modes)
        tier = self._tier_modes[self._current_tier_idx]
        self.tier_chip.setText(f"⚡ Mode: {tier.capitalize()}")
        self.tier_changed.emit(tier)

    def add_image_attachment(self, image_input: ImageInput) -> None:
        """Add an image attachment and refresh thumbnail view."""
        self._attached_images.append(image_input)
        self._refresh_attachments_ui()

    def remove_image_attachment(self, image_id: str) -> None:
        """Remove an image attachment by ID."""
        self._attached_images = [img for img in self._attached_images if img.id != image_id]
        self._refresh_attachments_ui()

    def clear_attachments(self) -> None:
        """Clear all attached images."""
        self._attached_images.clear()
        self._refresh_attachments_ui()

    def get_attached_images(self) -> list[ImageInput]:
        """Retrieve copy of currently attached images."""
        return list(self._attached_images)

    def _refresh_attachments_ui(self) -> None:
        """Rebuild the attachment thumbnail strip."""
        while self.attachment_layout.count() > 1:
            item = self.attachment_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._attached_images:
            for img in self._attached_images:
                thumb = ImageThumbnailWidget(img)
                thumb.remove_requested.connect(self.remove_image_attachment)
                self.attachment_layout.insertWidget(self.attachment_layout.count() - 1, thumb)
            self.attachment_bar.setVisible(True)
        else:
            self.attachment_bar.setVisible(False)

    def _handle_send(self) -> None:
        text = self.text_input.toPlainText().strip()
        if text or self._attached_images:
            effective_prompt = text if text else "Describe the attached image in detail."
            self.text_input.clear()
            self.send_submitted.emit(effective_prompt)

    def set_running_state(self, is_running: bool) -> None:
        """Toggle between Send and Stop buttons depending on agent execution state."""
        self.send_btn.setVisible(not is_running)
        self.stop_btn.setVisible(is_running)
        self.text_input.setEnabled(not is_running)
        self.mic_chip.setEnabled(not is_running)
        self.attach_chip.setEnabled(not is_running)
        self.screen_chip.setEnabled(not is_running)
        self.tier_chip.setEnabled(not is_running)
        if not is_running:
            self.text_input.setFocus()

    def set_voice_state(self, state: str, elapsed_seconds: int = 0) -> None:
        """Update visual presentation of the microphone chip based on voice state."""
        if state == "recording":
            mins = elapsed_seconds // 60
            secs = elapsed_seconds % 60
            time_str = f"{mins:02d}:{secs:02d}"
            self.mic_chip.setText("🔴")
            self.mic_chip.setToolTip(f"Recording ({time_str}) - Click to stop and transcribe")
            self.mic_chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_DANGER};
                    border: 1px solid #ffffff;
                    color: #ffffff;
                    font-size: 13px;
                    border-radius: 12px;
                    padding: 3px 10px;
                }}
            """)
        elif state == "transcribing":
            self.mic_chip.setText("◌")
            self.mic_chip.setToolTip("Transcribing speech locally with Faster-Whisper...")
            self.mic_chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_WARNING};
                    border: 1px solid {COLOR_BORDER};
                    color: #0b0e17;
                    font-size: 13px;
                    border-radius: 12px;
                    padding: 3px 10px;
                }}
            """)
        else:  # idle, completed, error
            self.mic_chip.setText("🎤")
            self.mic_chip.setStyleSheet("")

    def set_text(self, text: str) -> None:
        """Populate input box with transcribed speech for user review and editing."""
        if not text:
            return

        current = self.text_input.toPlainText()
        if current and not current.endswith((" ", "\n")):
            new_text = f"{current} {text}"
        elif current:
            new_text = f"{current}{text}"
        else:
            new_text = text

        self.text_input.setPlainText(new_text)
        cursor = self.text_input.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_input.setTextCursor(cursor)
        self.text_input.setFocus()
