"""System status bar widget showing real-time backend indicators, model selection, and audio states."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.ui.models import BackendStatus
from app.ui.theme import (
    COLOR_ACCENT,
    COLOR_BG_PANEL,
    COLOR_BG_SURFACE,
    COLOR_BORDER_SOLID,
    COLOR_DANGER,
    COLOR_PURPLE,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)


class SystemStatusBar(QWidget):
    """Bottom status bar displaying live backend connectivity, execution tier, tools, and audio states."""

    model_changed = Signal(str)
    refresh_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setStyleSheet(f"""
            SystemStatusBar {{
                background-color: {COLOR_BG_PANEL};
                border-top: 1px solid {COLOR_BORDER_SOLID};
                font-size: 11px;
                font-family: Consolas, "Segoe UI", sans-serif;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        # 1. Ollama Connection
        self.ollama_dot = QLabel("●")
        self.ollama_dot.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 10px;")
        self.ollama_label = QLabel("Ollama: Disconnected")
        self.ollama_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(self.ollama_dot)
        layout.addWidget(self.ollama_label)

        # 2. Model Selector & Tier Pill
        model_title = QLabel("Model:")
        model_title.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        self.model_combo = QComboBox()
        self.model_combo.setFixedWidth(140)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(model_title)
        layout.addWidget(self.model_combo)

        # Tier Pill Badge
        self.tier_badge = QLabel("TIER: STANDARD")
        self.tier_badge.setStyleSheet(f"""
            color: #00f2fe;
            background-color: rgba(0, 242, 254, 0.1);
            border: 1px solid #00f2fe;
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 9px;
            font-weight: 800;
        """)
        layout.addWidget(self.tier_badge)

        layout.addSpacing(6)

        # 3. Memory & Knowledge status
        self.memory_label = QLabel("🧠 Memory ●")
        self.memory_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        layout.addWidget(self.memory_label)

        self.knowledge_label = QLabel("📚 RAG ● (0 docs)")
        self.knowledge_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        layout.addWidget(self.knowledge_label)

        # 4. Browser status
        self.browser_label = QLabel("🌐 Browser: Ready")
        self.browser_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(self.browser_label)

        # 5. Microphone input status
        self.voice_label = QLabel("🎤 Mic: Ready")
        self.voice_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        layout.addWidget(self.voice_label)

        # 6. Speaker TTS output status
        self.tts_label = QLabel("🔊 Speaker: Ready")
        self.tts_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        layout.addWidget(self.tts_label)

        # 7. Automation status
        self.auto_label = QLabel("⚡ Auto: Active")
        self.auto_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        layout.addWidget(self.auto_label)

        # 8. Tools count
        self.tools_label = QLabel("⚙ Tools: 69")
        self.tools_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(self.tools_label)

        # 9. Performance indicator
        self.perf_label = QLabel("⚡ Latency: --")
        self.perf_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(self.perf_label)

        layout.addStretch()

        # Refresh button
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Refresh backend status")
        self.refresh_btn.setFixedSize(22, 22)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setStyleSheet(f"border: none; background: transparent; font-size: 13px; color: {COLOR_TEXT_MUTED};")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self.refresh_btn)

    def update_status(self, status: BackendStatus) -> None:
        """Update visual indicators from backend status snapshot."""
        if status.ollama_connected:
            self.ollama_dot.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 10px;")
            self.ollama_label.setText("Ollama: Connected")
        else:
            self.ollama_dot.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 10px;")
            self.ollama_label.setText("Ollama: Offline")

        # Populate model combo if changed
        if status.available_models:
            current = self.model_combo.currentText()
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            items = ["Auto (Intelligent)", "Fast", "Standard", "Heavy"] + [
                m for m in status.available_models if m not in ["Auto (Intelligent)", "Fast", "Standard", "Heavy"]
            ]
            self.model_combo.addItems(items)
            if current in items:
                self.model_combo.setCurrentText(current)
            elif status.model_name in items:
                self.model_combo.setCurrentText(status.model_name)
            else:
                self.model_combo.setCurrentText("Auto (Intelligent)")
            self.model_combo.blockSignals(False)

        self.knowledge_label.setText(f"📚 RAG ● ({status.docs_count} docs)")
        browser_state = "Active" if status.browser_active else "Ready"
        self.browser_label.setText(f"🌐 Browser: {browser_state}")
        self.tools_label.setText(f"⚙ Tools: {status.tools_count}")
        self.set_voice_state(status.voice_state, is_available=status.voice_ready)
        self.set_tts_state(status.tts_state, is_available=status.tts_ready)
        self.set_automation_state(status.automation_enabled)

    def set_performance_metric(self, model_name: str, latency_seconds: float, tok_per_sec: float = 0.0) -> None:
        """Update last response performance display."""
        if tok_per_sec > 0:
            self.perf_label.setText(f"⚡ {tok_per_sec:.1f} t/s • {latency_seconds:.2f}s")
        else:
            self.perf_label.setText(f"⚡ {latency_seconds:.2f}s ({model_name})")

    def set_tier_badge(self, tier_name: str) -> None:
        """Update active execution tier badge."""
        t_clean = tier_name.upper()
        self.tier_badge.setText(f"TIER: {t_clean}")
        if "FAST" in t_clean:
            self.tier_badge.setStyleSheet(f"color: #10b981; background-color: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;")
        elif "HEAVY" in t_clean:
            self.tier_badge.setStyleSheet(f"color: #a855f7; background-color: rgba(168, 85, 247, 0.1); border: 1px solid #a855f7; border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;")
        else:
            self.tier_badge.setStyleSheet(f"color: #00f2fe; background-color: rgba(0, 242, 254, 0.1); border: 1px solid #00f2fe; border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;")

    def set_automation_state(self, enabled: bool) -> None:
        """Update automation master indicator."""
        if enabled:
            self.auto_label.setText("⚡ Auto: Active")
            self.auto_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        else:
            self.auto_label.setText("⚡ Auto: Paused")
            self.auto_label.setStyleSheet(f"color: {COLOR_WARNING};")

    def set_voice_state(self, state: str, is_available: bool = True) -> None:
        """Update the microphone indicator state dynamically."""
        if state == "recording":
            self.voice_label.setText("🎤 Mic: 🔴 Recording")
            self.voice_label.setStyleSheet(f"color: {COLOR_DANGER}; font-weight: bold;")
        elif state == "transcribing":
            self.voice_label.setText("🎤 Mic: ◌ Transcribing")
            self.voice_label.setStyleSheet(f"color: {COLOR_WARNING};")
        elif is_available:
            self.voice_label.setText("🎤 Mic: Ready")
            self.voice_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        else:
            self.voice_label.setText("🎤 Mic: Off")
            self.voice_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")

    def set_tts_state(self, state: str, is_available: bool = True) -> None:
        """Update the speaker/TTS output indicator state dynamically."""
        if state == "speaking":
            self.tts_label.setText("🔊 Speaker: Speaking")
            self.tts_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-weight: bold;")
        elif state == "synthesizing":
            self.tts_label.setText("🔊 Speaker: ◌ Synthesizing")
            self.tts_label.setStyleSheet(f"color: {COLOR_WARNING};")
        elif is_available:
            self.tts_label.setText("🔊 Speaker: Ready")
            self.tts_label.setStyleSheet(f"color: {COLOR_SUCCESS};")
        else:
            self.tts_label.setText("🔊 Speaker: Off")
            self.tts_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")

    def _on_model_changed(self, text: str) -> None:
        if text:
            self.model_changed.emit(text)
            self.set_tier_badge(text)
