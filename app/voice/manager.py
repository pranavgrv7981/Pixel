"""Voice subsystem manager orchestrating microphone capture, STT engine, and temporary cleanup."""

from pathlib import Path
import time
from typing import Optional, Union

from app.core.config import Settings, get_settings
from app.core.exceptions import AudioRecordingError, SpeechToTextError, VoiceError
from app.core.logging import get_logger
from app.voice.audio import AudioRecorder, get_default_microphone, list_microphones, select_microphone
from app.voice.models import AudioDevice, TranscriptionResult, VoiceState, VoiceStatus
from app.voice.providers import FasterWhisperProvider, SpeechToTextProvider

logger = get_logger("voice.manager")


class VoiceManager:
    """Coordinates microphone recording, temporary file lifecycle, and speech transcription."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        stt_provider: Optional[SpeechToTextProvider] = None,
        recorder: Optional[AudioRecorder] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = stt_provider or FasterWhisperProvider(
            model_name=self.settings.stt_model,
            device=self.settings.stt_device,
            compute_type=self.settings.stt_compute_type,
        )
        self.recorder = recorder or AudioRecorder(
            sample_rate=self.settings.audio_sample_rate,
            channels=1,
        )
        self._current_state = VoiceState.IDLE
        self._selected_device: Optional[AudioDevice] = None

        # Resolve preferred microphone
        self._resolve_device()

    def _resolve_device(self) -> None:
        """Resolve current active microphone based on settings or system default."""
        try:
            self._selected_device = select_microphone(self.settings.selected_microphone)
            if self._selected_device:
                self.recorder.device_id = self._selected_device.id
        except Exception as err:
            logger.warning("Could not resolve microphone device: %s", err)

    @property
    def current_state(self) -> VoiceState:
        return self._current_state

    @property
    def selected_device(self) -> Optional[AudioDevice]:
        return self._selected_device

    def select_device(self, identifier: Optional[Union[str, int]]) -> Optional[AudioDevice]:
        """Update selected microphone device."""
        device = select_microphone(identifier)
        if device:
            self._selected_device = device
            self.recorder.device_id = device.id
            logger.info("Selected microphone updated to: %s (id=%d)", device.name, device.id)
        return self._selected_device

    def list_available_devices(self) -> list[AudioDevice]:
        """List all detected input microphone devices."""
        return list_microphones()

    def start_recording(self) -> None:
        """Begin audio capture from selected microphone."""
        if not self.settings.voice_enabled:
            raise VoiceError("Voice input is currently disabled in application settings")

        self._current_state = VoiceState.RECORDING
        try:
            self.recorder.start_recording(device_id=self.recorder.device_id)
        except Exception as err:
            self._current_state = VoiceState.ERROR
            raise

    def stop_recording(self) -> Path:
        """Stop audio capture and return temporary WAV path."""
        try:
            temp_wav = self.recorder.stop_recording()
            return temp_wav
        except Exception as err:
            self._current_state = VoiceState.ERROR
            raise

    def cancel_recording(self) -> None:
        """Cancel audio capture and discard buffer."""
        self.recorder.cancel_recording()
        self._current_state = VoiceState.IDLE

    def transcribe_audio_file(self, audio_path: Path, delete_after: bool = True) -> TranscriptionResult:
        """Transcribe an audio file and guarantee temporary file deletion."""
        self._current_state = VoiceState.TRANSCRIBING
        try:
            result = self.provider.transcribe(audio_path)
            self._current_state = VoiceState.COMPLETED
            return result
        except Exception as err:
            self._current_state = VoiceState.ERROR
            raise
        finally:
            if delete_after and audio_path.exists():
                try:
                    audio_path.unlink()
                    logger.debug("Deleted temporary audio file: %s", audio_path.name)
                except Exception as err:
                    logger.warning("Could not delete temporary audio file %s: %s", audio_path, err)

    def get_status(self) -> VoiceStatus:
        """Return diagnostic status snapshot of the voice subsystem."""
        default_dev = get_default_microphone()
        is_avail = self.provider.is_available() and (self._selected_device is not None or default_dev is not None)

        return VoiceStatus(
            enabled=self.settings.voice_enabled,
            state=self._current_state,
            selected_mic=self._selected_device.name if self._selected_device else None,
            default_mic=default_dev.name if default_dev else None,
            model_name=self.settings.stt_model,
            is_available=is_avail,
        )

    def shutdown(self) -> None:
        """Release audio streams and speech model weights on application exit."""
        logger.info("VoiceManager shutting down...")
        self.recorder.close()
        self.provider.unload()
        self._current_state = VoiceState.IDLE
