"""Unit tests for audio output device enumeration and sound playback."""

from pathlib import Path
import threading
from unittest.mock import MagicMock, patch
import wave
import numpy as np
import pytest

from app.core.exceptions import AudioPlaybackError
from app.voice.tts_audio import (
    AudioPlayer,
    get_default_output_device,
    list_output_devices,
    select_output_device,
)


@pytest.fixture
def mock_sd_output_devices():
    return [
        {"name": "Microsoft Sound Mapper - Output", "max_output_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
        {"name": "Speakers (Realtek Audio)", "max_output_channels": 2, "hostapi": 0, "default_samplerate": 48000.0},
        {"name": "Microphone (Realtek Audio)", "max_output_channels": 0, "hostapi": 0, "default_samplerate": 48000.0},
    ]


def test_list_output_devices(mock_sd_output_devices) -> None:
    with patch("sounddevice.query_devices", return_value=mock_sd_output_devices), \
         patch("sounddevice.query_hostapis", return_value={"name": "MME"}), \
         patch("sounddevice.default", new=MagicMock(device=(0, 1))):

        outputs = list_output_devices()
        assert len(outputs) == 2  # Microphone ignored (0 out channels)
        assert outputs[0].id == 0
        assert outputs[1].id == 1
        assert outputs[1].is_default is True


def test_get_default_output_device(mock_sd_output_devices) -> None:
    with patch("sounddevice.query_devices", return_value=mock_sd_output_devices), \
         patch("sounddevice.query_hostapis", return_value={"name": "MME"}), \
         patch("sounddevice.default", new=MagicMock(device=(0, 1))):

        default_dev = get_default_output_device()
        assert default_dev is not None
        assert default_dev.id == 1
        assert "Speakers" in default_dev.name


def test_select_output_device(mock_sd_output_devices) -> None:
    with patch("sounddevice.query_devices", return_value=mock_sd_output_devices), \
         patch("sounddevice.query_hostapis", return_value={"name": "MME"}), \
         patch("sounddevice.default", new=MagicMock(device=(0, 1))):

        dev_name = select_output_device("speakers")
        assert dev_name is not None
        assert dev_name.id == 1

        dev_id = select_output_device(0)
        assert dev_id is not None
        assert dev_id.id == 0


def test_audio_player_play_and_stop(tmp_path: Path) -> None:
    wav_file = tmp_path / "test_play.wav"
    sample_rate = 16000
    duration = 0.05
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    audio = (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16)

    with wave.open(str(wav_file), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())

    player = AudioPlayer()
    mock_stream = MagicMock()

    with patch("sounddevice.RawOutputStream", return_value=mock_stream):
        stop_evt = threading.Event()
        player.play_wav_file(wav_file, stop_event=stop_evt)
        mock_stream.start.assert_called_once()
        mock_stream.write.assert_called()


def test_audio_player_missing_file_raises(tmp_path: Path) -> None:
    player = AudioPlayer()
    non_existent = tmp_path / "missing.wav"
    with pytest.raises(AudioPlaybackError):
        player.play_wav_file(non_existent)
