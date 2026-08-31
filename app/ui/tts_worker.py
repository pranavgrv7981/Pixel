"""Background QThread worker for asynchronous text-to-speech synthesis and playback."""

from pathlib import Path
import threading
from typing import Any, Optional
from PySide6.QtCore import QThread, Signal

from app.core.exceptions import VoiceError
from app.core.logging import get_logger
from app.voice.tts_manager import TTSManager

logger = get_logger("ui.tts_worker")


class TTSPlaybackWorker(QThread):
    """Worker thread synthesizing and playing audio without blocking the Qt event loop."""

    started_playing = Signal(str)
    finished_playing = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        tts_manager: TTSManager,
        text: str,
        stop_event: Optional[threading.Event] = None,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.tts_manager = tts_manager
        self.text = text
        self.stop_event = stop_event or threading.Event()

    def stop(self) -> None:
        """Signal worker to stop playback and cancel pending synthesis."""
        self.stop_event.set()
        self.tts_manager.stop()

    def run(self) -> None:
        """Synthesize text and play audio locally."""
        logger.info("TTSPlaybackWorker started for text: '%.40s...'", self.text)
        try:
            self.started_playing.emit(self.text)
            self.tts_manager.synthesize_and_play(self.text, stop_event=self.stop_event)
            self.finished_playing.emit()
        except VoiceError as err:
            logger.error("TTS playback worker domain error: %s", err)
            self.error_occurred.emit(str(err))
        except Exception as err:
            logger.exception("Unexpected error in TTS playback worker: %s", err)
            self.error_occurred.emit(f"Speech output error: {err}")
