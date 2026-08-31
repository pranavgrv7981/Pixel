"""Microphone enumeration, device selection, and local audio recording via sounddevice."""

from pathlib import Path
import tempfile
import threading
from typing import Any, Optional, Union
import wave

import numpy as np
import sounddevice as sd

from app.core.exceptions import AudioRecordingError, MicrophoneUnavailableError
from app.core.logging import get_logger
from app.voice.models import AudioDevice

logger = get_logger("voice.audio")


def list_microphones() -> list[AudioDevice]:
    """Enumerate available audio input devices (microphones)."""
    devices: list[AudioDevice] = []
    try:
        raw_devices = sd.query_devices()
        default_in, _ = sd.default.device

        for idx, dev in enumerate(raw_devices):
            max_in = dev.get("max_input_channels", 0)
            if max_in > 0:
                hostapi_idx = dev.get("hostapi", 0)
                try:
                    hostapi_info = sd.query_hostapis(hostapi_idx)
                    hostapi_name = hostapi_info.get("name", "Unknown")
                except Exception:
                    hostapi_name = "Unknown"

                is_default = (idx == default_in)
                devices.append(
                    AudioDevice(
                        id=idx,
                        name=dev.get("name", f"Microphone {idx}"),
                        hostapi=hostapi_name,
                        max_input_channels=max_in,
                        default_samplerate=dev.get("default_samplerate", 16000.0),
                        is_default=is_default,
                    )
                )
    except Exception as err:
        logger.warning("Failed to enumerate audio devices: %s", err)

    return devices


def get_default_microphone() -> Optional[AudioDevice]:
    """Retrieve the primary/default input microphone device."""
    devices = list_microphones()
    for d in devices:
        if d.is_default:
            return d
    return devices[0] if devices else None


def select_microphone(identifier: Optional[Union[str, int]] = None) -> Optional[AudioDevice]:
    """Resolve an AudioDevice by index or name substring; falls back to default device."""
    devices = list_microphones()
    if not devices:
        return None

    if identifier is None:
        return get_default_microphone()

    if isinstance(identifier, int):
        for d in devices:
            if d.id == identifier:
                return d

    if isinstance(identifier, str) and identifier.strip():
        search = identifier.strip().lower()
        # Exact ID match string
        if search.isdigit():
            target_id = int(search)
            for d in devices:
                if d.id == target_id:
                    return d
        # Substring match
        for d in devices:
            if search in d.name.lower():
                return d

    return get_default_microphone()


class AudioRecorder:
    """Captures microphone input stream to temporary 16 kHz 16-bit mono WAV files."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device_id: Optional[int] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_id = device_id
        self._stream: Optional[sd.InputStream] = None
        self._buffer: list[np.ndarray] = []
        self._is_recording = False
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        """Callback invoked by PortAudio for each captured audio block."""
        if status:
            logger.debug("Audio input stream callback warning: %s", status)
        with self._lock:
            if self._is_recording:
                self._buffer.append(indata.copy())

    def start_recording(self, device_id: Optional[int] = None) -> None:
        """Begin capturing audio from selected microphone."""
        if self._is_recording:
            logger.warning("start_recording requested while already recording.")
            return

        target_dev = device_id if device_id is not None else self.device_id

        # Verify device exists
        if target_dev is not None:
            try:
                info = sd.query_devices(target_dev)
                if info.get("max_input_channels", 0) <= 0:
                    raise MicrophoneUnavailableError(f"Device {target_dev} has no input channels")
            except Exception as err:
                raise MicrophoneUnavailableError(f"Microphone device {target_dev} is unavailable: {err}") from err

        with self._lock:
            self._buffer.clear()
            self._is_recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=target_dev,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("Started audio recording (device=%s, rate=%d, channels=%d)", target_dev, self.sample_rate, self.channels)
        except Exception as err:
            self._is_recording = False
            self._stream = None
            logger.error("Failed to start audio input stream: %s", err)
            raise AudioRecordingError(f"Could not initialize audio capture: {err}") from err

    def stop_recording(self) -> Path:
        """Stop capturing audio and write recorded samples to a temporary WAV file."""
        if not self._is_recording:
            raise AudioRecordingError("Cannot stop recording: recorder is not currently active")

        with self._lock:
            self._is_recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as err:
                logger.warning("Error closing audio stream: %s", err)
            finally:
                self._stream = None

        with self._lock:
            captured_blocks = list(self._buffer)
            self._buffer.clear()

        if not captured_blocks:
            raise AudioRecordingError("No audio samples were captured during the recording session")

        # Concatenate audio chunks
        full_audio = np.concatenate(captured_blocks, axis=0)

        # Write to secure temporary WAV file
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()

        try:
            with wave.open(str(temp_path), "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(self.sample_rate)
                wf.writeframes(full_audio.tobytes())
            logger.info("Saved audio recording (%d frames, %.2fs) to %s", len(full_audio), len(full_audio) / self.sample_rate, temp_path)
            return temp_path
        except Exception as err:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            logger.error("Failed to write temporary WAV audio: %s", err)
            raise AudioRecordingError(f"Failed to encode recorded audio to WAV: {err}") from err

    def cancel_recording(self) -> None:
        """Discard recorded buffer and terminate audio stream without saving."""
        with self._lock:
            self._is_recording = False
            self._buffer.clear()

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as err:
                logger.warning("Error aborting audio stream: %s", err)
            finally:
                self._stream = None
        logger.info("Audio recording cancelled and stream closed.")

    def close(self) -> None:
        """Ensure all streaming resources are released cleanly."""
        self.cancel_recording()
