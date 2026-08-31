"""Unit tests for voice subsystem data models and enums."""

import pytest

from app.voice.models import AudioDevice, TranscriptionResult, VoiceState, VoiceStatus


def test_voice_state_values() -> None:
    assert VoiceState.IDLE.value == "idle"
    assert VoiceState.RECORDING.value == "recording"
    assert VoiceState.TRANSCRIBING.value == "transcribing"
    assert VoiceState.COMPLETED.value == "completed"
    assert VoiceState.ERROR.value == "error"


def test_audio_device_model() -> None:
    dev = AudioDevice(
        id=1,
        name="Microphone (Realtek Audio)",
        hostapi="WASAPI",
        max_input_channels=2,
        default_samplerate=48000.0,
        is_default=True,
    )
    assert dev.id == 1
    assert dev.display_name == "Microphone (Realtek Audio) (Default)"

    dev_non_default = AudioDevice(
        id=2,
        name="USB Mic",
        hostapi="MME",
        max_input_channels=1,
        default_samplerate=16000.0,
        is_default=False,
    )
    assert dev_non_default.display_name == "USB Mic"


def test_transcription_result_model() -> None:
    res = TranscriptionResult(
        text="Open the document and summarize section 2.",
        language="en",
        duration=3.5,
        provider="faster-whisper-base",
    )
    assert res.text == "Open the document and summarize section 2."
    assert res.language == "en"
    assert res.duration == 3.5
    assert res.provider == "faster-whisper-base"


def test_voice_status_defaults() -> None:
    status = VoiceStatus()
    assert status.enabled is True
    assert status.state == VoiceState.IDLE
    assert status.model_name == "base"
    assert status.is_available is True
