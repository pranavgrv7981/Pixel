"""TTS controller managing speech queues, worker execution, and audio playback state."""

from collections import deque
import threading
from typing import Optional
from PySide6.QtCore import QObject, Signal

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ui.tts_worker import TTSPlaybackWorker
from app.voice.tts_manager import TTSManager
from app.voice.tts_models import TTSState, TTSStatus

logger = get_logger("ui.tts_controller")


class TTSController(QObject):
    """Coordinates speech queue, worker dispatch, audio stop control, and auto-speak responses."""

    tts_state_changed = Signal(str)     # TTSState.value
    speech_started = Signal(str)        # text being spoken
    speech_finished = Signal()
    tts_error = Signal(str)

    def __init__(
        self,
        tts_manager: TTSManager,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.tts_manager = tts_manager
        self.settings = settings or getattr(tts_manager, "settings", None) or get_settings()

        self._queue: deque[str] = deque()
        self._active_worker: Optional[TTSPlaybackWorker] = None
        self._state = TTSState.IDLE
        self._stop_event = threading.Event()

    @property
    def current_state(self) -> TTSState:
        return self._state

    def is_speaking(self) -> bool:
        return self._state in (TTSState.SPEAKING, TTSState.SYNTHESIZING)

    def set_state(self, state: TTSState) -> None:
        """Update TTS state and notify UI listeners."""
        self._state = state
        self.tts_state_changed.emit(state.value)

    def speak_text(self, text: str, interrupt_current: bool = False) -> None:
        """Enqueue or immediately play speech for given text."""
        if not text or not text.strip():
            return

        if not self.settings.tts_enabled:
            logger.debug("speak_text ignored: TTS is disabled.")
            return

        if interrupt_current:
            self.stop_speaking()
            self._queue.append(text)
            self._play_next()
        else:
            self._queue.append(text)
            if self._active_worker is None or not self._active_worker.isRunning():
                self._play_next()

    def _play_next(self) -> None:
        """Process the next speech utterance from the queue."""
        if not self._queue:
            self.set_state(TTSState.IDLE)
            self.speech_finished.emit()
            return

        next_text = self._queue.popleft()
        self._stop_event.clear()
        self.set_state(TTSState.SPEAKING)
        self.speech_started.emit(next_text)

        worker = TTSPlaybackWorker(
            tts_manager=self.tts_manager,
            text=next_text,
            stop_event=self._stop_event,
        )
        self._active_worker = worker
        worker.finished_playing.connect(self._on_worker_finished)
        worker.error_occurred.connect(self._on_worker_error)
        worker.start()

    def _on_worker_finished(self) -> None:
        """Handle worker completion on the Qt UI thread."""
        self._active_worker = None
        self._play_next()

    def _on_worker_error(self, err_msg: str) -> None:
        """Handle worker error on the Qt UI thread."""
        logger.error("TTS playback encountered an error: %s", err_msg)
        self._active_worker = None
        self.tts_error.emit(err_msg)
        self._play_next()

    def stop_speaking(self) -> None:
        """Immediately stop active playback and clear pending speech queue."""
        logger.info("Stopping TTS playback and clearing queue (%d items)", len(self._queue))
        self._queue.clear()
        self._stop_event.set()

        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.stop()
            self._active_worker.wait(1000)
            self._active_worker = None

        self.tts_manager.stop()
        self.set_state(TTSState.IDLE)
        self.speech_finished.emit()

    def clear_queue(self) -> None:
        """Clear queued speech without stopping currently playing speech."""
        self._queue.clear()

    def handle_turn_completed(self, assistant_response: str) -> None:
        """Callback invoked when assistant completes a message turn."""
        if self.settings.auto_speak_responses and self.settings.tts_enabled:
            logger.info("Auto-speaking completed assistant response...")
            self.speak_text(assistant_response)

    def get_status(self) -> TTSStatus:
        """Return diagnostic status snapshot."""
        return self.tts_manager.get_status()
