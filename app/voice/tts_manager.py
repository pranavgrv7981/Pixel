"""TTS Manager coordinating text sanitization, speech synthesis, and secure audio playback."""

from pathlib import Path
import tempfile
import threading
import time
from typing import Optional, Union

from app.core.config import Settings, get_settings
from app.core.exceptions import AudioPlaybackError, TextToSpeechError, VoiceError
from app.core.logging import get_logger
from app.voice.text_sanitizer import sanitize_text_for_speech
from app.voice.tts_audio import (
    AudioPlayer,
    get_default_output_device,
    list_output_devices,
    select_output_device,
)
from app.voice.tts_models import (
    AudioOutputDevice,
    TTSResult,
    TTSState,
    TTSStatus,
    VoiceInfo,
)
from app.voice.tts_providers import Pyttsx3Provider, TextToSpeechProvider

logger = get_logger("voice.tts_manager")


class TTSManager:
    """Orchestrates speech synthesis, playback output routing, and temporary file lifecycle."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        provider: Optional[TextToSpeechProvider] = None,
        player: Optional[AudioPlayer] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or Pyttsx3Provider(
            voice_id=self.settings.tts_voice,
            speed_rate=self.settings.tts_speed_rate,
        )
        self.player = player or AudioPlayer()
        self._current_state = TTSState.IDLE
        self._selected_output_device: Optional[AudioOutputDevice] = None

        self._resolve_output_device()

    def _resolve_output_device(self) -> None:
        """Resolve active audio output device based on settings or system default."""
        try:
            self._selected_output_device = select_output_device(self.settings.selected_audio_output)
            if self._selected_output_device:
                self.player.device_id = self._selected_output_device.id
        except Exception as err:
            logger.warning("Could not resolve audio output device: %s", err)

    @property
    def current_state(self) -> TTSState:
        return self._current_state

    @property
    def selected_output_device(self) -> Optional[AudioOutputDevice]:
        return self._selected_output_device

    def select_output_device(self, identifier: Optional[Union[str, int]]) -> Optional[AudioOutputDevice]:
        """Update selected audio output device."""
        device = select_output_device(identifier)
        if device:
            self._selected_output_device = device
            self.player.device_id = device.id
            logger.info("Selected audio output updated to: %s (id=%d)", device.name, device.id)
        return self._selected_output_device

    def list_available_voices(self) -> list[VoiceInfo]:
        """List all voices supported by the current TTS engine."""
        return self.provider.list_voices()

    def list_output_devices(self) -> list[AudioOutputDevice]:
        """List all detected audio playback devices."""
        return list_output_devices()

    def synthesize_and_play(
        self,
        text: str,
        stop_event: Optional[threading.Event] = None,
    ) -> list[TTSResult]:
        """Sanitize text, synthesize bounded segments, and stream audio locally."""
        if not self.settings.tts_enabled:
            raise VoiceError("Text-to-speech is disabled in application settings")

        segments = sanitize_text_for_speech(text, max_chars=self.settings.max_tts_characters)
        if not segments:
            logger.info("No synthesizeable text found after sanitization.")
            return []

        results: list[TTSResult] = []

        for idx, segment in enumerate(segments):
            if stop_event and stop_event.is_set():
                logger.info("TTS processing cancelled before segment %d", idx)
                break

            temp_wav = Path(tempfile.gettempdir()) / f"tts_speech_{int(time.time()*1000)}_{idx}.wav"
            self._current_state = TTSState.SYNTHESIZING

            try:
                # 1. Synthesize to temporary WAV
                res = self.provider.synthesize_to_file(
                    text=segment,
                    output_path=temp_wav,
                    voice_id=self.settings.tts_voice,
                    speed_rate=self.settings.tts_speed_rate,
                )
                results.append(res)

                if stop_event and stop_event.is_set():
                    break

                # 2. Play audio stream
                self._current_state = TTSState.SPEAKING
                logger.info("Playing synthesized speech segment %d/%d (%s)...", idx + 1, len(segments), temp_wav.name)
                self.player.play_wav_file(
                    wav_path=temp_wav,
                    device_id=self.player.device_id,
                    stop_event=stop_event,
                )

            except Exception as err:
                self._current_state = TTSState.ERROR
                logger.error("TTS processing error on segment %d: %s", idx, err)
                raise
            finally:
                # 3. Strictly clean up temporary WAV file
                if temp_wav.exists():
                    try:
                        temp_wav.unlink()
                        logger.debug("Deleted temporary TTS audio file: %s", temp_wav.name)
                    except Exception as err:
                        logger.warning("Could not delete temporary TTS audio file %s: %s", temp_wav, err)

        self._current_state = TTSState.IDLE
        return results

    def stop(self) -> None:
        """Halt active playback immediately."""
        self._current_state = TTSState.STOPPING
        self.player.stop()
        self._current_state = TTSState.IDLE

    def get_status(self) -> TTSStatus:
        """Return diagnostic status snapshot of the text-to-speech subsystem."""
        default_out = get_default_output_device()
        is_avail = self.provider.is_available()

        return TTSStatus(
            enabled=self.settings.tts_enabled,
            state=self._current_state,
            auto_speak=self.settings.auto_speak_responses,
            selected_voice=self.settings.tts_voice,
            selected_output=self._selected_output_device.name if self._selected_output_device else (default_out.name if default_out else None),
            is_available=is_avail,
        )

    def shutdown(self) -> None:
        """Cleanly stop playback and release TTS resources."""
        logger.info("TTSManager shutting down...")
        self.stop()
        self.provider.unload()
        self._current_state = TTSState.IDLE
