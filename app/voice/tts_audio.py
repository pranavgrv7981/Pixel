"""Audio output device enumeration and local sound playback via sounddevice."""

from pathlib import Path
import threading
import time
from typing import Optional, Union
import wave

import sounddevice as sd

from app.core.exceptions import AudioPlaybackError
from app.core.logging import get_logger
from app.voice.tts_models import AudioOutputDevice

logger = get_logger("voice.tts_audio")


def list_output_devices() -> list[AudioOutputDevice]:
    """Enumerate available audio output devices (speakers / headphones)."""
    devices: list[AudioOutputDevice] = []
    try:
        raw_devices = sd.query_devices()
        _, default_out = sd.default.device

        for idx, dev in enumerate(raw_devices):
            max_out = dev.get("max_output_channels", 0)
            if max_out > 0:
                hostapi_idx = dev.get("hostapi", 0)
                try:
                    hostapi_info = sd.query_hostapis(hostapi_idx)
                    hostapi_name = hostapi_info.get("name", "Unknown")
                except Exception:
                    hostapi_name = "Unknown"

                is_default = (idx == default_out)
                devices.append(
                    AudioOutputDevice(
                        id=idx,
                        name=dev.get("name", f"Speaker {idx}"),
                        hostapi=hostapi_name,
                        max_output_channels=max_out,
                        default_samplerate=dev.get("default_samplerate", 44100.0),
                        is_default=is_default,
                    )
                )
    except Exception as err:
        logger.warning("Failed to enumerate audio output devices: %s", err)

    return devices


def get_default_output_device() -> Optional[AudioOutputDevice]:
    """Retrieve the system default audio playback device."""
    devices = list_output_devices()
    for d in devices:
        if d.is_default:
            return d
    return devices[0] if devices else None


def select_output_device(identifier: Optional[Union[str, int]] = None) -> Optional[AudioOutputDevice]:
    """Resolve an AudioOutputDevice by index or name substring; falls back to default device."""
    devices = list_output_devices()
    if not devices:
        return None

    if identifier is None:
        return get_default_output_device()

    if isinstance(identifier, int):
        for d in devices:
            if d.id == identifier:
                return d

    if isinstance(identifier, str) and identifier.strip():
        search = identifier.strip().lower()
        if search.isdigit():
            target_id = int(search)
            for d in devices:
                if d.id == target_id:
                    return d
        for d in devices:
            if search in d.name.lower():
                return d

    return get_default_output_device()


class AudioPlayer:
    """Streams audio WAV files to selected output devices with responsive cancellation support."""

    def __init__(self, device_id: Optional[int] = None) -> None:
        self.device_id = device_id
        self._current_stream: Optional[sd.RawOutputStream] = None
        self._is_playing = False
        self._lock = threading.Lock()

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def play_wav_file(
        self,
        wav_path: Path,
        device_id: Optional[int] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Stream a WAV audio file to the output device."""
        if not wav_path.exists() or wav_path.stat().st_size == 0:
            raise AudioPlaybackError(f"WAV audio file '{wav_path}' does not exist or is empty")

        target_dev = device_id if device_id is not None else self.device_id

        try:
            with wave.open(str(wav_path), "rb") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                dtype = "int16" if sample_width == 2 else "uint8"

                with self._lock:
                    self._is_playing = True

                stream = sd.RawOutputStream(
                    samplerate=sample_rate,
                    channels=channels,
                    dtype=dtype,
                    device=target_dev,
                )
                with self._lock:
                    self._current_stream = stream

                stream.start()

                # Stream in chunks (2048 frames ~ 50-100ms) to allow instant cancellation
                chunk_frames = 2048
                chunk_bytes = chunk_frames * channels * sample_width

                try:
                    while self._is_playing:
                        if stop_event and stop_event.is_set():
                            logger.info("Playback interrupted by stop event.")
                            break

                        data = wf.readframes(chunk_frames)
                        if not data:
                            break
                        stream.write(data)
                finally:
                    with self._lock:
                        self._is_playing = False
                        if self._current_stream:
                            try:
                                self._current_stream.stop()
                                self._current_stream.close()
                            except Exception:
                                pass
                            self._current_stream = None

        except Exception as err:
            with self._lock:
                self._is_playing = False
                self._current_stream = None
            if stop_event and stop_event.is_set():
                return
            logger.error("Audio playback error for %s: %s", wav_path.name, err)
            raise AudioPlaybackError(f"Failed to play audio on device {target_dev}: {err}") from err

    def stop(self) -> None:
        """Immediately halt audio output streaming."""
        with self._lock:
            self._is_playing = False
            if self._current_stream is not None:
                try:
                    self._current_stream.stop()
                    self._current_stream.close()
                except Exception:
                    pass
                self._current_stream = None
        logger.info("AudioPlayer playback stopped.")
