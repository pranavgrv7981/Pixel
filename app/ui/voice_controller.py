"""Voice controller managing audio recording, timers, and transcription worker dispatch."""

from typing import Optional
from PySide6.QtCore import QObject, QTimer, Signal

from app.core.config import Settings, get_settings
from app.core.exceptions import VoiceError
from app.core.logging import get_logger
from app.ui.voice_worker import VoiceTranscriptionWorker
from app.voice.manager import VoiceManager
from app.voice.models import TranscriptionResult, VoiceState, VoiceStatus

logger = get_logger("ui.voice_controller")


class VoiceController(QObject):
    """Coordinates microphone recording, UI state, timers, and asynchronous transcription."""

    voice_state_changed = Signal(str)         # VoiceState.value
    recording_duration_tick = Signal(int)    # elapsed seconds
    transcription_ready = Signal(str)        # transcribed text
    voice_error = Signal(str)
    microphone_changed = Signal(str)

    def __init__(
        self,
        voice_manager: VoiceManager,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.voice_manager = voice_manager
        self.settings = settings or getattr(voice_manager, "settings", None) or get_settings()


        self._state = VoiceState.IDLE
        self._elapsed_seconds = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_timer_tick)

        self._active_worker: Optional[VoiceTranscriptionWorker] = None

    @property
    def current_state(self) -> VoiceState:
        return self._state

    def set_state(self, state: VoiceState) -> None:
        """Transition voice state and emit signal to listeners."""
        self._state = state
        self.voice_state_changed.emit(state.value)

    def is_recording(self) -> bool:
        return self._state == VoiceState.RECORDING

    def is_transcribing(self) -> bool:
        return self._state == VoiceState.TRANSCRIBING

    def toggle_recording(self) -> None:
        """Convenience method to toggle between start and stop recording."""
        if self._state == VoiceState.RECORDING:
            self.stop_recording()
        elif self._state in (VoiceState.IDLE, VoiceState.COMPLETED, VoiceState.ERROR):
            self.start_recording()

    def start_recording(self) -> None:
        """Initiate audio recording from microphone."""
        if self._state == VoiceState.RECORDING:
            return

        if not self.settings.voice_enabled:
            self.voice_error.emit("Voice input is disabled in settings.")
            return

        try:
            self.voice_manager.start_recording()
            self._elapsed_seconds = 0
            self.set_state(VoiceState.RECORDING)
            self._timer.start()
            self.recording_duration_tick.emit(0)
            logger.info("VoiceController started recording.")
        except Exception as err:
            self.set_state(VoiceState.ERROR)
            logger.error("Failed to start voice recording: %s", err)
            self.voice_error.emit(f"Microphone error: {err}")

    def stop_recording(self) -> None:
        """Stop audio recording and launch asynchronous transcription worker."""
        if self._state != VoiceState.RECORDING:
            return

        self._timer.stop()
        try:
            temp_wav = self.voice_manager.stop_recording()
            self.set_state(VoiceState.TRANSCRIBING)
            logger.info("VoiceController stopped recording; starting transcription worker for %s", temp_wav.name)

            worker = VoiceTranscriptionWorker(
                voice_manager=self.voice_manager,
                audio_path=temp_wav,
            )
            self._active_worker = worker
            worker.transcription_completed.connect(self._on_transcription_completed)
            worker.error_occurred.connect(self._on_transcription_error)
            worker.start()

        except Exception as err:
            self.set_state(VoiceState.ERROR)
            logger.error("Failed to stop voice recording: %s", err)
            self.voice_error.emit(f"Recording error: {err}")

    def cancel_recording(self) -> None:
        """Abort recording and discard captured audio buffer."""
        self._timer.stop()
        self.voice_manager.cancel_recording()
        self.set_state(VoiceState.IDLE)
        self.recording_duration_tick.emit(0)
        logger.info("VoiceController cancelled recording.")

    def _on_timer_tick(self) -> None:
        """Handle 1-second interval timer during active recording."""
        self._elapsed_seconds += 1
        self.recording_duration_tick.emit(self._elapsed_seconds)

        max_sec = self.settings.max_recording_seconds
        if self._elapsed_seconds >= max_sec:
            logger.info("Maximum recording limit reached (%ds); stopping automatically.", max_sec)
            self.stop_recording()

    def _on_transcription_completed(self, result: TranscriptionResult) -> None:
        """Handle worker completion on the main UI thread."""
        self.set_state(VoiceState.IDLE)
        self._active_worker = None
        logger.info("Transcription received: '%s'", result.text[:50])
        self.transcription_ready.emit(result.text)

    def _on_transcription_error(self, error_message: str) -> None:
        """Handle worker failure on the main UI thread."""
        self.set_state(VoiceState.ERROR)
        self._active_worker = None
        self.voice_error.emit(error_message)

    def get_status(self) -> VoiceStatus:
        """Return diagnostic status snapshot."""
        return self.voice_manager.get_status()
