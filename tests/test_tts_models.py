"""Unit tests for text-to-speech data models and enums."""

from pathlib import Path
import pytest

from app.voice.tts_models import (
    AudioOutputDevice,
    TTSResult,
    TTSState,
    TTSStatus,
    VoiceInfo,
)


def test_tts_state_values() -> None:
    assert TTSState.IDLE.value == "idle"
    assert TTSState.SYNTHESIZING.value == "synthesizing"
    assert TTSState.SPEAKING.value == "speaking"
    assert TTSState.STOPPING.value == "stopping"
    assert TTSState.ERROR.value == "error"


def test_voice_info_model() -> None:
    voice = VoiceInfo(
        id="HKEY_LOCAL_MACHINE\\...\\DAVID",
        name="Microsoft David Desktop",
        language="en-US",
        gender="Male",
    )
    assert voice.id == "HKEY_LOCAL_MACHINE\\...\\DAVID"
    assert voice.name == "Microsoft David Desktop"
    assert voice.display_name == "Microsoft David Desktop"


def test_audio_output_device_model() -> None:
    device = AudioOutputDevice(
        id=3,
        name="Speakers (Realtek Audio)",
        hostapi="WASAPI",
        max_output_channels=2,
        default_samplerate=48000.0,
        is_default=True,
    )
    assert device.id == 3
    assert device.display_name == "Speakers (Realtek Audio) (Default)"

    device_non_default = AudioOutputDevice(
        id=5,
        name="Headphones",
        hostapi="MME",
        max_output_channels=2,
        default_samplerate=44100.0,
        is_default=False,
    )
    assert device_non_default.display_name == "Headphones"


def test_tts_result_model(tmp_path: Path) -> None:
    dummy_wav = tmp_path / "speech.wav"
    dummy_wav.write_bytes(b"RIFFdummy")

    result = TTSResult(
        audio_path=dummy_wav,
        duration=2.4,
        text="The calculation result is 210.",
        voice="Microsoft David",
        provider="pyttsx3",
        success=True,
    )
    assert result.duration == 2.4
    assert result.text == "The calculation result is 210."
    assert result.voice == "Microsoft David"
    assert result.success is True


def test_tts_status_defaults() -> None:
    status = TTSStatus()
    assert status.enabled is True
    assert status.state == TTSState.IDLE
    assert status.auto_speak is False
    assert status.is_available is True
