"""Unit tests for audio device enumeration and audio recording buffers."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import wave
import numpy as np
import pytest

from app.core.exceptions import AudioRecordingError, MicrophoneUnavailableError
from app.voice.audio import AudioRecorder, get_default_microphone, list_microphones, select_microphone
from app.voice.models import AudioDevice


@pytest.fixture
def mock_sd_devices():
    return [
        {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
        {"name": "Microphone (Realtek Audio)", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 48000.0},
        {"name": "Speakers (Realtek Audio)", "max_input_channels": 0, "hostapi": 0, "default_samplerate": 48000.0},
    ]


def test_list_microphones(mock_sd_devices) -> None:
    with patch("sounddevice.query_devices", return_value=mock_sd_devices), \
         patch("sounddevice.query_hostapis", return_value={"name": "MME"}), \
         patch("sounddevice.default", new=MagicMock(device=(1, 2))):

        mics = list_microphones()
        assert len(mics) == 2  # Speakers ignored (0 in channels)
        assert mics[0].id == 0
        assert mics[1].id == 1
        assert mics[1].is_default is True


def test_get_default_microphone(mock_sd_devices) -> None:
    with patch("sounddevice.query_devices", return_value=mock_sd_devices), \
         patch("sounddevice.query_hostapis", return_value={"name": "MME"}), \
         patch("sounddevice.default", new=MagicMock(device=(1, 2))):

        default_mic = get_default_microphone()
        assert default_mic is not None
        assert default_mic.id == 1
        assert "Realtek" in default_mic.name


def test_select_microphone(mock_sd_devices) -> None:
    with patch("sounddevice.query_devices", return_value=mock_sd_devices), \
         patch("sounddevice.query_hostapis", return_value={"name": "MME"}), \
         patch("sounddevice.default", new=MagicMock(device=(1, 2))):

        # By substring
        dev = select_microphone("realtek")
        assert dev is not None
        assert dev.id == 1

        # By ID string
        dev_id = select_microphone("0")
        assert dev_id is not None
        assert dev_id.id == 0

        # By integer ID
        dev_int = select_microphone(1)
        assert dev_int is not None
        assert dev_int.id == 1


def test_audio_recorder_buffer_and_wav_generation() -> None:
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    assert not recorder.is_recording

    # Simulate recording buffer accumulation
    block1 = np.ones((1600, 1), dtype=np.int16) * 100
    block2 = np.ones((1600, 1), dtype=np.int16) * 200

    recorder._is_recording = True
    recorder._audio_callback(block1, 1600, None, None)
    recorder._audio_callback(block2, 1600, None, None)

    wav_path = recorder.stop_recording()
    try:
        assert wav_path.exists()
        assert wav_path.suffix == ".wav"

        # Validate WAV structure
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2  # 16-bit
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 3200
    finally:
        if wav_path.exists():
            wav_path.unlink()


def test_audio_recorder_cancel() -> None:
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    recorder._is_recording = True
    recorder._buffer.append(np.zeros((100, 1), dtype=np.int16))

    recorder.cancel_recording()
    assert not recorder.is_recording
    assert len(recorder._buffer) == 0


def test_audio_recorder_stop_when_idle_raises() -> None:
    recorder = AudioRecorder()
    with pytest.raises(AudioRecordingError):
        recorder.stop_recording()
