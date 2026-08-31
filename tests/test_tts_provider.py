"""Unit tests for Text-to-Speech providers."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.exceptions import TextToSpeechError
from app.voice.tts_providers import MockTTSProvider, Pyttsx3Provider


def test_mock_tts_provider_success(tmp_path: Path) -> None:
    provider = MockTTSProvider()
    assert provider.is_available()
    assert not provider.is_loaded()

    provider.load()
    assert provider.is_loaded()

    voices = provider.list_voices()
    assert len(voices) == 2
    assert voices[0].id == "mock-voice-1"

    out_file = tmp_path / "mock_speech.wav"
    result = provider.synthesize_to_file("Hello from the assistant.", out_file)

    assert result.success is True
    assert result.audio_path == out_file
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    provider.unload()
    assert not provider.is_loaded()


def test_mock_tts_provider_failure(tmp_path: Path) -> None:
    provider = MockTTSProvider(should_fail=True, failure_message="TTS engine crashed")
    out_file = tmp_path / "fail.wav"

    with pytest.raises(TextToSpeechError, match="TTS engine crashed"):
        provider.synthesize_to_file("Some prompt", out_file)


def test_pyttsx3_provider_empty_text_raises(tmp_path: Path) -> None:
    provider = Pyttsx3Provider()
    out_file = tmp_path / "empty.wav"

    with pytest.raises(TextToSpeechError, match="empty speech"):
        provider.synthesize_to_file("", out_file)


def test_pyttsx3_provider_list_voices_mocked() -> None:
    mock_voice = MagicMock()
    mock_voice.id = "HKEY_LOCAL_MACHINE\\...\\ZIRA"
    mock_voice.name = "Microsoft Zira Desktop"
    mock_voice.languages = ["en-US"]
    mock_voice.gender = "Female"

    mock_engine = MagicMock()
    mock_engine.getProperty.return_value = [mock_voice]

    with patch("pyttsx3.init", return_value=mock_engine):
        provider = Pyttsx3Provider()
        voices = provider.list_voices()
        assert len(voices) == 1
        assert voices[0].name == "Microsoft Zira Desktop"
