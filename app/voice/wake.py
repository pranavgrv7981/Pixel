"""Voice wake phrase detection and low-resource microphone listening for Pixel."""

import io
import math
import re
import string
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional
import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Signal

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.voice.models import TranscriptionResult
from app.voice.providers import FasterWhisperProvider, SpeechToTextProvider

logger = get_logger("voice.wake")


class WakePhraseValidator:
    """Validates transcriptions against strict Pixel wake commands with false-wake rejection."""

    # Normalized exact wake phrases accepted
    VALID_WAKE_PHRASES: set[str] = {
        "pixel open",
        "open pixel",
        "hey pixel",
        "hey pixel open",
        "hi pixel",
        "hi pixel open",
        "pixel please open",
        "pixel wakeup",
        "wake up pixel",
    }

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Strip punctuation, lowercase, and collapse whitespace."""
        if not text:
            return ""
        # Lowercase
        t = text.lower()
        # Remove punctuation
        t = re.sub(r"[^\w\s]", " ", t)
        # Collapse multiple whitespaces
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @classmethod
    def is_wake_command(cls, transcription: str, assistant_name: str = "pixel") -> bool:
        """Evaluate if transcription contains an authentic Pixel summon command."""
        norm = cls.normalize_text(transcription)
        if not norm:
            return False

        # 1. Exact match check
        if norm in cls.VALID_WAKE_PHRASES:
            return True

        # 2. Check for assistant name + "open"
        name_lower = assistant_name.lower()
        words = norm.split()

        # Reject single words or general chatter without clear activation intent
        if len(words) < 2:
            if norm == name_lower:
                return True
            return False

        # Reject obvious false wake contexts
        negative_keywords = {
            "display", "screen", "camera", "phone", "image", "resolution",
            "broken", "dead", "google", "buy", "price", "review", "art",
            "drawing", "canvas", "dimension", "width", "height", "color"
        }
        if any(kw in words for kw in negative_keywords):
            return False

        # Must explicitly contain assistant name
        if name_lower not in words:
            return False

        # Check valid activation combinations:
        # e.g. ["pixel", "open"], ["open", "pixel"], ["hey", "pixel", "open"]
        if (words == [name_lower, "open"] or
            words == ["open", name_lower] or
            words == ["hey", name_lower] or
            words == ["hey", name_lower, "open"] or
            words == ["hi", name_lower, "open"]):
            return True

        return False


class VoiceWakeDetector(QObject):
    """Low-resource background audio listener detecting Pixel wake commands."""

    wake_detected = Signal(str)

    def __init__(
        self,
        settings: Optional[Settings] = None,
        stt_provider: Optional[SpeechToTextProvider] = None,
        on_wake: Optional[Callable[[str], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or get_settings()
        self.stt_provider = stt_provider or FasterWhisperProvider(
            model_name=self.settings.stt_model,
            device=self.settings.stt_device,
            compute_type=self.settings.stt_compute_type,
        )
        if on_wake:
            self.wake_detected.connect(on_wake)

        self._is_enabled = self.settings.voice_wake_enabled
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._sample_rate = 16000
        self._window_duration = 2.5  # seconds
        self._energy_threshold = 0.015  # RMS energy threshold for speech trigger
        self._cooldown_seconds = 2.0
        self._last_wake_time = 0.0

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    @property
    def is_running(self) -> bool:
        return self._is_running

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable voice wake detection."""
        self._is_enabled = enabled
        self.settings.voice_wake_enabled = enabled
        logger.info("Voice wake detector enabled set to: %s", enabled)
        if enabled and not self._is_running:
            self.start()
        elif not enabled and self._is_running:
            self.stop()

    def start(self) -> bool:
        """Start background wake word monitoring thread."""
        if not self._is_enabled:
            logger.info("Voice wake is disabled in settings; not starting listener.")
            return False

        if self._is_running:
            return True

        self._is_running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="VoiceWakeListener",
            daemon=True,
        )
        self._thread.start()
        logger.info("Voice wake detector started listening for '%s'.", self.settings.pixel_name)
        return True

    def stop(self) -> None:
        """Stop background wake word monitoring cleanly."""
        if not self._is_running:
            return

        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        logger.info("Voice wake detector stopped.")

    def _listen_loop(self) -> None:
        """Background audio capture with energy-gated transcription."""
        buffer_size = int(self._sample_rate * self._window_duration)
        audio_ring = np.zeros(buffer_size, dtype=np.float32)
        write_idx = 0
        speech_detected = False
        speech_frames_count = 0

        chunk_size = 1024

        def audio_callback(indata, frames, time_info, status):
            nonlocal write_idx, audio_ring, speech_detected, speech_frames_count
            if not self._is_running:
                return

            samples = indata[:, 0]
            # Calculate RMS energy
            rms = np.sqrt(np.mean(samples ** 2)) if len(samples) > 0 else 0.0

            # Store in circular ring buffer
            end_idx = write_idx + len(samples)
            if end_idx <= buffer_size:
                audio_ring[write_idx:end_idx] = samples
                write_idx = end_idx % buffer_size
            else:
                part1 = buffer_size - write_idx
                audio_ring[write_idx:] = samples[:part1]
                part2 = len(samples) - part1
                audio_ring[:part2] = samples[part1:]
                write_idx = part2

            if rms > self._energy_threshold:
                speech_frames_count += 1
                if speech_frames_count >= 3:
                    speech_detected = True
            else:
                if speech_frames_count > 0:
                    speech_frames_count -= 1

        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                blocksize=chunk_size,
                callback=audio_callback,
            ):
                while self._is_running:
                    time.sleep(0.3)
                    if speech_detected and (time.time() - self._last_wake_time) > self._cooldown_seconds:
                        speech_detected = False
                        # Extract linear buffer from ring
                        ordered_audio = np.concatenate((audio_ring[write_idx:], audio_ring[:write_idx]))
                        self._process_candidate_audio(ordered_audio)
        except Exception as err:
            logger.warning("Voice wake audio stream encountered error: %s", err)
            self._is_running = False

    def _process_candidate_audio(self, audio_data: np.ndarray) -> None:
        """Save candidate buffer to temporary WAV and verify with STT provider."""
        temp_wav = None
        try:
            # Convert float32 [-1.0, 1.0] to int16
            int16_data = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_wav = Path(f.name)

            with wave.open(str(temp_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate)
                wf.writeframes(int16_data.tobytes())

            result: TranscriptionResult = self.stt_provider.transcribe(temp_wav)
            text = result.text.strip()
            logger.debug("Wake candidate transcription: '%s'", text)

            if WakePhraseValidator.is_wake_command(text, assistant_name=self.settings.pixel_name):
                logger.info("Authentic Pixel wake command detected: '%s'!", text)
                self._last_wake_time = time.time()
                self.wake_detected.emit(text)

        except Exception as err:
            logger.warning("Error processing wake audio candidate: %s", err)
        finally:
            if temp_wav and temp_wav.exists():
                try:
                    temp_wav.unlink(missing_ok=True)
                except Exception:
                    pass
