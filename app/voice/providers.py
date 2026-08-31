"""Speech-to-Text provider abstraction and local Faster-Whisper implementation."""

from abc import ABC, abstractmethod
from pathlib import Path
import time
from typing import Optional

from app.core.exceptions import SpeechToTextError
from app.core.logging import get_logger
from app.voice.models import TranscriptionResult

logger = get_logger("voice.stt")


class SpeechToTextProvider(ABC):
    """Abstract interface for local speech-to-text transcription providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether provider engine dependencies are installed and available."""
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check whether the model weights are currently resident in memory."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Load speech recognition model weights into memory."""
        pass

    @abstractmethod
    def unload(self) -> None:
        """Release speech recognition model weights from memory."""
        pass

    @abstractmethod
    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe an audio file to text."""
        pass


class FasterWhisperProvider(SpeechToTextProvider):
    """Local, offline speech recognition using faster-whisper (CTranslate2)."""

    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: Optional[Path] = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self._model = None

    def is_available(self) -> bool:
        """Return True if faster_whisper can be imported."""
        try:
            import faster_whisper
            return True
        except ImportError:
            return False

    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Lazy load WhisperModel on CPU/GPU."""
        if self._model is not None:
            return

        logger.info(
            "Loading FasterWhisper model '%s' (device=%s, compute_type=%s)...",
            self.model_name,
            self.device,
            self.compute_type,
        )
        try:
            from faster_whisper import WhisperModel

            root = str(self.download_root) if self.download_root else None
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                download_root=root,
            )
            logger.info("FasterWhisper model '%s' loaded successfully.", self.model_name)
        except Exception as err:
            logger.error("Failed to load FasterWhisper model '%s': %s", self.model_name, err)
            raise SpeechToTextError(f"Could not load speech model '{self.model_name}': {err}") from err

    def unload(self) -> None:
        """Unload WhisperModel to reclaim RAM."""
        if self._model is not None:
            logger.info("Unloading FasterWhisper model '%s'.", self.model_name)
            self._model = None

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio file using local WhisperModel."""
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise SpeechToTextError(f"Audio file '{audio_path}' is missing or empty")

        if self._model is None:
            self.load()

        start_time = time.time()
        logger.info("Starting local transcription for: %s", audio_path.name)

        try:
            segments, info = self._model.transcribe(
                str(audio_path),
                beam_size=5,
                vad_filter=True,
            )
            text_segments = [s.text.strip() for s in segments]
            full_text = " ".join(t for t in text_segments if t).strip()
            duration = getattr(info, "duration", 0.0) or (time.time() - start_time)
            language = getattr(info, "language", None)

            logger.info("Transcription completed (duration=%.2fs, lang=%s): '%s'", duration, language, full_text[:60])
            return TranscriptionResult(
                text=full_text,
                language=language,
                duration=duration,
                provider=f"faster-whisper-{self.model_name}",
            )
        except Exception as err:
            logger.error("Transcription failed for audio '%s': %s", audio_path.name, err)
            raise SpeechToTextError(f"Local speech transcription failed: {err}") from err


class MockSpeechToTextProvider(SpeechToTextProvider):
    """Deterministic mock provider for unit and integration tests."""

    def __init__(
        self,
        mock_text: str = "Hello assistant, this is a voice test.",
        language: str = "en",
        should_fail: bool = False,
        failure_message: str = "Simulated transcription error",
    ) -> None:
        self.mock_text = mock_text
        self.language = language
        self.should_fail = should_fail
        self.failure_message = failure_message
        self._loaded = False

    def is_available(self) -> bool:
        return True

    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        if not audio_path.exists():
            raise SpeechToTextError(f"File not found: {audio_path}")
        if self.should_fail:
            raise SpeechToTextError(self.failure_message)

        return TranscriptionResult(
            text=self.mock_text,
            language=self.language,
            duration=1.5,
            provider="mock-stt",
        )
