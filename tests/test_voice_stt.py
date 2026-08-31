"""Unit tests for Speech-to-Text providers and transcription models."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.exceptions import SpeechToTextError
from app.voice.providers import FasterWhisperProvider, MockSpeechToTextProvider


def test_mock_stt_provider_success(tmp_path: Path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFFdummywavdata")

    provider = MockSpeechToTextProvider(mock_text="Hello world test", language="en")
    assert provider.is_available()
    assert not provider.is_loaded()

    provider.load()
    assert provider.is_loaded()

    result = provider.transcribe(audio_file)
    assert result.text == "Hello world test"
    assert result.language == "en"
    assert result.provider == "mock-stt"

    provider.unload()
    assert not provider.is_loaded()


def test_mock_stt_provider_failure(tmp_path: Path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFFdummywavdata")

    provider = MockSpeechToTextProvider(should_fail=True, failure_message="Model error")
    with pytest.raises(SpeechToTextError, match="Model error"):
        provider.transcribe(audio_file)


def test_faster_whisper_lazy_loading(tmp_path: Path) -> None:
    provider = FasterWhisperProvider(model_name="tiny", device="cpu", compute_type="int8")
    assert provider.is_available()
    assert not provider.is_loaded()

    mock_segment = MagicMock()
    mock_segment.text = "This is a transcribed sentence."
    mock_info = MagicMock(language="en", duration=2.1)

    mock_whisper_model = MagicMock()
    mock_whisper_model.transcribe.return_value = ([mock_segment], mock_info)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"RIFFsamplewavdata")

    with patch("faster_whisper.WhisperModel", return_value=mock_whisper_model):
        result = provider.transcribe(audio_file)
        assert provider.is_loaded()
        assert result.text == "This is a transcribed sentence."
        assert result.language == "en"
        assert result.provider == "faster-whisper-tiny"

        provider.unload()
        assert not provider.is_loaded()


def test_stt_missing_file_raises(tmp_path: Path) -> None:
    provider = FasterWhisperProvider()
    non_existent = tmp_path / "missing.wav"
    with pytest.raises(SpeechToTextError):
        provider.transcribe(non_existent)
