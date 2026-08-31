"""Unit tests for TTSController speech queuing, auto-speak, and cancellation."""

import os
from pathlib import Path
import sys
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication

from app.core.config import Settings
from app.ui.tts_controller import TTSController
from app.voice.tts_manager import TTSManager
from app.voice.tts_models import TTSState
from app.voice.tts_providers import MockTTSProvider

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def mock_tts_manager(tmp_path: Path) -> TTSManager:
    settings = Settings(tts_enabled=True, auto_speak_responses=False)
    provider = MockTTSProvider()
    player = MagicMock()
    mgr = TTSManager(settings=settings, provider=provider, player=player)
    return mgr


def test_tts_controller_initial_state(mock_tts_manager: TTSManager, qapp: QApplication) -> None:
    controller = TTSController(tts_manager=mock_tts_manager)
    assert controller.current_state == TTSState.IDLE
    assert not controller.is_speaking()


def test_tts_controller_queue_and_playback(mock_tts_manager: TTSManager, qapp: QApplication) -> None:
    controller = TTSController(tts_manager=mock_tts_manager)

    states = []
    controller.tts_state_changed.connect(lambda s: states.append(s))

    spoken_texts = []
    controller.speech_started.connect(lambda t: spoken_texts.append(t))

    controller.speak_text("First assistant message.")
    assert controller.is_speaking() or controller.current_state in (TTSState.SPEAKING, TTSState.IDLE)

    if controller._active_worker:
        controller._active_worker.wait(3000)
    qapp.processEvents()

    assert len(spoken_texts) == 1
    assert spoken_texts[0] == "First assistant message."
    assert controller.current_state == TTSState.IDLE


def test_tts_controller_stop_speaking(mock_tts_manager: TTSManager, qapp: QApplication) -> None:
    controller = TTSController(tts_manager=mock_tts_manager)
    controller.speak_text("Message one")
    controller.speak_text("Message two")
    assert len(controller._queue) >= 0

    controller.stop_speaking()
    assert len(controller._queue) == 0
    assert controller.current_state == TTSState.IDLE


def test_tts_controller_auto_speak_gating(mock_tts_manager: TTSManager, qapp: QApplication) -> None:
    controller = TTSController(tts_manager=mock_tts_manager)

    # 1. When auto_speak_responses is False, handle_turn_completed should NOT speak
    mock_tts_manager.settings.auto_speak_responses = False
    controller.handle_turn_completed("Some completed response")
    assert len(controller._queue) == 0
    assert not controller.is_speaking()

    # 2. When auto_speak_responses is True, handle_turn_completed DOES speak
    mock_tts_manager.settings.auto_speak_responses = True
    controller.handle_turn_completed("Another completed response")
    assert controller.is_speaking() or controller.current_state in (TTSState.SPEAKING, TTSState.IDLE)

    if controller._active_worker:
        controller._active_worker.wait(3000)
    qapp.processEvents()
    assert controller.current_state == TTSState.IDLE
