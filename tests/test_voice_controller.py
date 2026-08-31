"""Unit tests for VoiceController state coordination and worker dispatch."""

import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.core.config import Settings
from app.ui.voice_controller import VoiceController
from app.voice.manager import VoiceManager
from app.voice.models import TranscriptionResult, VoiceState
from app.voice.providers import MockSpeechToTextProvider

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def mock_voice_manager(tmp_path: Path) -> VoiceManager:
    settings = Settings(voice_enabled=True, max_recording_seconds=5)
    stt = MockSpeechToTextProvider(mock_text="Mock voice transcription test")
    recorder = MagicMock()
    fake_wav = tmp_path / "fake.wav"
    fake_wav.write_bytes(b"RIFFfake")
    recorder.stop_recording.return_value = fake_wav

    mgr = VoiceManager(settings=settings, stt_provider=stt, recorder=recorder)
    return mgr


def test_voice_controller_initial_state(mock_voice_manager: VoiceManager, qapp: QApplication) -> None:
    controller = VoiceController(voice_manager=mock_voice_manager)
    assert controller.current_state == VoiceState.IDLE
    assert not controller.is_recording()
    assert not controller.is_transcribing()


def test_voice_controller_recording_and_transcription(mock_voice_manager: VoiceManager, qapp: QApplication) -> None:
    controller = VoiceController(voice_manager=mock_voice_manager)

    states_recorded = []
    controller.voice_state_changed.connect(lambda s: states_recorded.append(s))

    transcription_out = []
    controller.transcription_ready.connect(lambda t: transcription_out.append(t))

    controller.start_recording()
    assert controller.is_recording()
    assert controller.current_state == VoiceState.RECORDING

    controller.stop_recording()
    assert controller.is_transcribing() or controller.current_state == VoiceState.TRANSCRIBING

    # Wait for background worker to finish
    if controller._active_worker:
        controller._active_worker.wait(3000)

    qapp.processEvents()

    assert controller.current_state == VoiceState.IDLE
    assert len(transcription_out) == 1
    assert transcription_out[0] == "Mock voice transcription test"
    assert "recording" in states_recorded
    assert "transcribing" in states_recorded


def test_voice_controller_cancel(mock_voice_manager: VoiceManager, qapp: QApplication) -> None:
    controller = VoiceController(voice_manager=mock_voice_manager)
    controller.start_recording()
    assert controller.is_recording()

    controller.cancel_recording()
    assert controller.current_state == VoiceState.IDLE
    assert not controller.is_recording()


def test_voice_controller_max_duration_limit(mock_voice_manager: VoiceManager, qapp: QApplication) -> None:
    mock_voice_manager.settings.max_recording_seconds = 2
    controller = VoiceController(voice_manager=mock_voice_manager)

    states_recorded = []
    controller.voice_state_changed.connect(lambda s: states_recorded.append(s))

    controller.start_recording()
    controller._elapsed_seconds = 1
    # Trigger tick reaching max
    controller._on_timer_tick()

    if controller._active_worker:
        controller._active_worker.wait(3000)
    qapp.processEvents()

    assert "transcribing" in states_recorded
    assert controller.current_state == VoiceState.IDLE

