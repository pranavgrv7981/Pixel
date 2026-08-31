"""Settings dialog for inspecting and adjusting application preferences."""

from typing import Optional
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Settings
from app.ui.theme import COLOR_BORDER
from app.voice.audio import list_microphones
from app.voice.tts_audio import list_output_devices
from app.voice.tts_providers import Pyttsx3Provider


class SettingsDialog(QDialog):
    """Configuration dialog for viewing and adjusting non-destructive system settings."""

    def __init__(self, settings: Settings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Assistant Settings")
        self.setFixedWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel("Application Settings")
        header.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(8)

        # 1. Model & Ollama
        self.ollama_url = QLineEdit(settings.ollama_base_url)
        form.addRow("Ollama Base URL:", self.ollama_url)

        self.default_model = QLineEdit(settings.default_model)
        form.addRow("Default Model:", self.default_model)

        self.max_messages = QSpinBox()
        self.max_messages.setRange(10, 500)
        self.max_messages.setValue(settings.max_conversation_messages)
        form.addRow("Max Messages:", self.max_messages)

        self.rag_top_k = QSpinBox()
        self.rag_top_k.setRange(1, 20)
        self.rag_top_k.setValue(settings.rag_top_k)
        form.addRow("RAG Retrieval Top-K:", self.rag_top_k)

        self.browser_headless = QCheckBox("Run Browser Headless")
        self.browser_headless.setChecked(settings.browser_headless)
        form.addRow("Browser Mode:", self.browser_headless)

        # 2. Voice Input (Phase 12)
        voice_header = QLabel("Voice Input (Local STT)")
        voice_header.setStyleSheet("font-weight: 600; color: #7aa2f7; margin-top: 6px;")
        form.addRow(voice_header)

        self.voice_enabled = QCheckBox("Enable Voice Speech-to-Text")
        self.voice_enabled.setChecked(settings.voice_enabled)
        form.addRow("Voice Input:", self.voice_enabled)

        self.stt_model_combo = QComboBox()
        self.stt_model_combo.addItems(["tiny", "base", "small", "medium"])
        if settings.stt_model in ["tiny", "base", "small", "medium"]:
            self.stt_model_combo.setCurrentText(settings.stt_model)
        form.addRow("Speech Model:", self.stt_model_combo)

        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Default System Microphone", None)
        try:
            mics = list_microphones()
            for m in mics:
                self.mic_combo.addItem(m.display_name, m.name)
            if settings.selected_microphone:
                idx = self.mic_combo.findData(settings.selected_microphone)
                if idx >= 0:
                    self.mic_combo.setCurrentIndex(idx)
        except Exception:
            pass
        form.addRow("Microphone:", self.mic_combo)

        self.max_recording = QSpinBox()
        self.max_recording.setRange(5, 300)
        self.max_recording.setValue(settings.max_recording_seconds)
        form.addRow("Max Recording (sec):", self.max_recording)

        # 3. Voice Output (Phase 13 - TTS)
        tts_header = QLabel("Voice Output (Local TTS)")
        tts_header.setStyleSheet("font-weight: 600; color: #a6e3a1; margin-top: 6px;")
        form.addRow(tts_header)

        self.tts_enabled = QCheckBox("Enable Text-to-Speech")
        self.tts_enabled.setChecked(settings.tts_enabled)
        form.addRow("Voice Output:", self.tts_enabled)

        self.auto_speak = QCheckBox("Auto-Speak Responses (OFF by default)")
        self.auto_speak.setChecked(settings.auto_speak_responses)
        form.addRow("Auto Speak:", self.auto_speak)

        self.tts_voice_combo = QComboBox()
        self.tts_voice_combo.addItem("Default System Voice", None)
        try:
            provider = Pyttsx3Provider()
            voices = provider.list_voices()
            for v in voices:
                self.tts_voice_combo.addItem(v.display_name, v.id)
            if settings.tts_voice:
                idx = self.tts_voice_combo.findData(settings.tts_voice)
                if idx >= 0:
                    self.tts_voice_combo.setCurrentIndex(idx)
        except Exception:
            pass
        form.addRow("TTS Voice:", self.tts_voice_combo)

        self.speed_rate_spin = QSpinBox()
        self.speed_rate_spin.setRange(100, 300)
        self.speed_rate_spin.setValue(settings.tts_speed_rate)
        form.addRow("Speech Rate (WPM):", self.speed_rate_spin)

        self.audio_output_combo = QComboBox()
        self.audio_output_combo.addItem("Default Playback Device", None)
        try:
            outputs = list_output_devices()
            for o in outputs:
                self.audio_output_combo.addItem(o.display_name, o.name)
            if settings.selected_audio_output:
                idx = self.audio_output_combo.findData(settings.selected_audio_output)
                if idx >= 0:
                    self.audio_output_combo.setCurrentIndex(idx)
        except Exception:
            pass
        form.addRow("Audio Output:", self.audio_output_combo)

        # 4. Context & Personalization (Phase 17)
        context_header = QLabel("Context & Personalization")
        context_header.setStyleSheet("font-weight: 600; color: #f5c2e7; margin-top: 6px;")
        form.addRow(context_header)

        self.context_enabled_cb = QCheckBox("Enable Context Management")
        self.context_enabled_cb.setChecked(getattr(settings, "context_management_enabled", True))
        form.addRow("Context Manager:", self.context_enabled_cb)

        self.response_style_combo = QComboBox()
        self.response_style_combo.addItems(["balanced", "concise", "detailed"])
        current_style = getattr(settings, "default_response_style", "balanced").lower()
        if current_style in ["balanced", "concise", "detailed"]:
            self.response_style_combo.setCurrentText(current_style)
        form.addRow("Response Style:", self.response_style_combo)

        self.recent_msgs_spin = QSpinBox()
        self.recent_msgs_spin.setRange(2, 50)
        self.recent_msgs_spin.setValue(getattr(settings, "recent_messages_count", 8))
        form.addRow("Recent Messages Depth:", self.recent_msgs_spin)

        self.auto_sys_cb = QCheckBox("Automatic System Metrics Context")
        self.auto_sys_cb.setChecked(getattr(settings, "auto_system_context_enabled", True))
        form.addRow("System Context:", self.auto_sys_cb)

        # 5. Intelligence & Quality (Phase 18)
        intel_header = QLabel("Intelligence & Autonomy (Phase 18)")
        intel_header.setStyleSheet("font-weight: 600; color: #a6e3a1; margin-top: 6px;")
        form.addRow(intel_header)

        self.autonomy_combo = QComboBox()
        self.autonomy_combo.addItems(["assisted", "confirm_actions", "controlled_autonomous"])
        cur_autonomy = getattr(settings, "autonomy_level", "confirm_actions").lower()
        if cur_autonomy in ["assisted", "confirm_actions", "controlled_autonomous"]:
            self.autonomy_combo.setCurrentText(cur_autonomy)
        form.addRow("Autonomy Level:", self.autonomy_combo)

        self.quality_checks_cb = QCheckBox("Enable Response Quality & False-Completion Checks")
        self.quality_checks_cb.setChecked(getattr(settings, "quality_checks_enabled", True))
        form.addRow("Quality Checks:", self.quality_checks_cb)

        self.quality_telemetry_cb = QCheckBox("Record Local Interaction Telemetry")
        self.quality_telemetry_cb.setChecked(getattr(settings, "quality_telemetry_enabled", True))
        form.addRow("Quality Telemetry:", self.quality_telemetry_cb)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _save_settings(self) -> None:
        self.settings.ollama_base_url = self.ollama_url.text().strip()
        self.settings.default_model = self.default_model.text().strip()
        self.settings.max_conversation_messages = self.max_messages.value()
        self.settings.rag_top_k = self.rag_top_k.value()
        self.settings.browser_headless = self.browser_headless.isChecked()

        # Save voice input settings
        self.settings.voice_enabled = self.voice_enabled.isChecked()
        self.settings.stt_model = self.stt_model_combo.currentText()
        self.settings.selected_microphone = self.mic_combo.currentData()
        self.settings.max_recording_seconds = self.max_recording.value()

        # Save voice output settings (Phase 13)
        self.settings.tts_enabled = self.tts_enabled.isChecked()
        self.settings.auto_speak_responses = self.auto_speak.isChecked()
        self.settings.tts_voice = self.tts_voice_combo.currentData()
        self.settings.tts_speed_rate = self.speed_rate_spin.value()
        self.settings.selected_audio_output = self.audio_output_combo.currentData()

        # Save context & personalization settings (Phase 17)
        self.settings.context_management_enabled = self.context_enabled_cb.isChecked()
        self.settings.default_response_style = self.response_style_combo.currentText()
        self.settings.recent_messages_count = self.recent_msgs_spin.value()
        self.settings.auto_system_context_enabled = self.auto_sys_cb.isChecked()

        # Save intelligence & quality settings (Phase 18)
        self.settings.autonomy_level = self.autonomy_combo.currentText()
        self.settings.quality_checks_enabled = self.quality_checks_cb.isChecked()
        self.settings.quality_telemetry_enabled = self.quality_telemetry_cb.isChecked()

        self.accept()
