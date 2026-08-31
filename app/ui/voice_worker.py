"""Background QThread worker executing speech-to-text transcription asynchronously."""

from pathlib import Path
from typing import Any, Optional
from PySide6.QtCore import QThread, Signal

from app.core.exceptions import VoiceError
from app.core.logging import get_logger
from app.voice.manager import VoiceManager
from app.voice.models import TranscriptionResult

logger = get_logger("ui.voice_worker")


class VoiceTranscriptionWorker(QThread):
    """Worker thread running STT transcription off the Qt UI thread."""

    transcription_completed = Signal(object)  # TranscriptionResult
    error_occurred = Signal(str)

    def __init__(
        self,
        voice_manager: VoiceManager,
        audio_path: Path,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.voice_manager = voice_manager
        self.audio_path = audio_path

    def run(self) -> None:
        """Transcribe temporary audio and emit completion signal."""
        logger.info("VoiceTranscriptionWorker starting transcription for: %s", self.audio_path.name)
        try:
            result = self.voice_manager.transcribe_audio_file(self.audio_path, delete_after=True)
            self.transcription_completed.emit(result)
        except VoiceError as err:
            logger.error("Voice transcription domain error: %s", err)
            self.error_occurred.emit(str(err))
        except Exception as err:
            logger.exception("Unexpected error during voice transcription: %s", err)
            self.error_occurred.emit(f"Speech transcription error: {err}")
