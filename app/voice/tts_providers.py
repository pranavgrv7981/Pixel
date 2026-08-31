"""Text-to-Speech provider abstraction and local engine implementations."""

from abc import ABC, abstractmethod
from pathlib import Path
import time
from typing import Optional
import wave
import numpy as np

from app.core.exceptions import TextToSpeechError
from app.core.logging import get_logger
from app.voice.tts_models import TTSResult, VoiceInfo

logger = get_logger("voice.tts_providers")


class TextToSpeechProvider(ABC):
    """Abstract interface for local text-to-speech synthesis providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether provider engine dependencies are installed and available."""
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check whether the synthesis engine/model is resident in memory."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Load synthesis engine resources."""
        pass

    @abstractmethod
    def unload(self) -> None:
        """Release synthesis engine resources."""
        pass

    @abstractmethod
    def list_voices(self) -> list[VoiceInfo]:
        """List available local voices supported by this engine."""
        pass

    @abstractmethod
    def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        voice_id: Optional[str] = None,
        speed_rate: int = 175,
    ) -> TTSResult:
        """Synthesize text to an output WAV audio file."""
        pass


class Pyttsx3Provider(TextToSpeechProvider):
    """Local, offline TTS engine using pyttsx3 (native Windows SAPI5)."""

    def __init__(self, voice_id: Optional[str] = None, speed_rate: int = 175) -> None:
        self.default_voice_id = voice_id
        self.speed_rate = speed_rate
        self._engine = None

    def is_available(self) -> bool:
        try:
            import pyttsx3
            return True
        except ImportError:
            return False

    def is_loaded(self) -> bool:
        return self._engine is not None

    def load(self) -> None:
        if self._engine is not None:
            return
        logger.info("Initializing pyttsx3 text-to-speech engine...")
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            if self.default_voice_id:
                try:
                    self._engine.setProperty("voice", self.default_voice_id)
                except Exception as err:
                    logger.warning("Could not set default voice '%s': %s", self.default_voice_id, err)
            self._engine.setProperty("rate", self.speed_rate)
            logger.info("pyttsx3 engine initialized.")
        except Exception as err:
            logger.error("Failed to initialize pyttsx3: %s", err)
            raise TextToSpeechError(f"Could not initialize pyttsx3 TTS engine: {err}") from err

    def unload(self) -> None:
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
            self._engine = None
            logger.info("pyttsx3 engine unloaded.")

    def list_voices(self) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        try:
            import pyttsx3
            temp_engine = pyttsx3.init()
            raw_voices = temp_engine.getProperty("voices") or []
            for v in raw_voices:
                voices.append(
                    VoiceInfo(
                        id=str(getattr(v, "id", "")),
                        name=str(getattr(v, "name", "Default Voice")),
                        language=str(getattr(v, "languages", ["en"])[0]) if getattr(v, "languages", None) else "en",
                        gender=str(getattr(v, "gender", None)) if getattr(v, "gender", None) else None,
                    )
                )
            temp_engine.stop()
        except Exception as err:
            logger.warning("Failed to enumerate pyttsx3 voices: %s", err)
        return voices

    def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        voice_id: Optional[str] = None,
        speed_rate: int = 175,
    ) -> TTSResult:
        if not text or not text.strip():
            raise TextToSpeechError("Cannot synthesize empty speech text")

        start_time = time.time()
        logger.info("Synthesizing speech with pyttsx3 (chars=%d) -> %s", len(text), output_path.name)

        try:
            import pyttsx3

            # Initialize a dedicated engine instance per synthesis for thread-safety
            engine = pyttsx3.init()
            target_voice = voice_id or self.default_voice_id
            if target_voice:
                try:
                    engine.setProperty("voice", target_voice)
                except Exception as err:
                    logger.warning("Could not set voice '%s': %s", target_voice, err)

            engine.setProperty("rate", speed_rate or self.speed_rate)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
            engine.stop()

            elapsed = time.time() - start_time
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise TextToSpeechError(f"Synthesized audio file was not generated: {output_path}")

            # Read duration from generated WAV
            duration = elapsed
            try:
                with wave.open(str(output_path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    duration = frames / float(rate)
            except Exception:
                pass

            logger.info("TTS synthesis complete (audio_duration=%.2fs, gen_time=%.2fs)", duration, elapsed)
            return TTSResult(
                audio_path=output_path,
                duration=duration,
                text=text,
                voice=target_voice or "default",
                provider="pyttsx3",
                success=True,
            )
        except Exception as err:
            logger.error("TTS synthesis error: %s", err)
            raise TextToSpeechError(f"Speech synthesis failed: {err}") from err


class MockTTSProvider(TextToSpeechProvider):
    """Deterministic mock TTS provider for unit and integration testing."""

    def __init__(self, should_fail: bool = False, failure_message: str = "Simulated TTS error") -> None:
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

    def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="mock-voice-1", name="Mock Voice One", language="en"),
            VoiceInfo(id="mock-voice-2", name="Mock Voice Two", language="en"),
        ]

    def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        voice_id: Optional[str] = None,
        speed_rate: int = 175,
    ) -> TTSResult:
        if self.should_fail:
            raise TextToSpeechError(self.failure_message)

        if not text or not text.strip():
            raise TextToSpeechError("Cannot synthesize empty speech text")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Create a valid 0.1s WAV file
        sample_rate = 16000
        duration = 0.1
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        audio = (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16)

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())

        return TTSResult(
            audio_path=output_path,
            duration=duration,
            text=text,
            voice=voice_id or "mock-voice-1",
            provider="mock-tts",
            success=True,
        )
