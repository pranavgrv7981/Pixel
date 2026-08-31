"""End-to-end integration tests for voice capture, transcription review, and agent execution."""

import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from app.agent.agent import Agent
from app.agent.conversation import Conversation, ConversationManager
from app.browser import BrowserManager
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.knowledge import KnowledgeManager
from app.memory import MemoryManager
from app.security.manager import PermissionManager
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.controller import AssistantController
from app.ui.main_window import MainWindow
from app.ui.voice_controller import VoiceController
from app.voice.manager import VoiceManager
from app.voice.models import VoiceState
from app.voice.providers import MockSpeechToTextProvider

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def voice_gui_fixture(tmp_path: Path, qapp: QApplication):
    settings = Settings(voice_enabled=True, max_recording_seconds=10)

    stt = MockSpeechToTextProvider(mock_text="What is the system uptime?")
    recorder = MagicMock()
    fake_wav = tmp_path / "test_audio.wav"
    fake_wav.write_bytes(b"RIFFdummydata")
    recorder.stop_recording.return_value = fake_wav

    voice_manager = VoiceManager(settings=settings, stt_provider=stt, recorder=recorder)
    voice_controller = VoiceController(voice_manager=voice_manager, settings=settings)

    client = MagicMock(spec=OllamaClient)
    client.default_model = "llama3"
    client.get_status.return_value = MagicMock(
        is_connected=True,
        base_url="http://localhost:11434",
        is_model_available=True,
        available_models=["llama3"],
    )

    conv_mgr = MagicMock(spec=ConversationManager)
    conv = Conversation(conversation_id="conv-voice")
    conv_mgr.create_conversation.return_value = conv
    conv_mgr.load_conversation.return_value = conv
    conv_mgr.list_conversations.return_value = []

    mem_mgr = MagicMock(spec=MemoryManager)
    know_mgr = MagicMock(spec=KnowledgeManager)
    know_mgr.list_documents.return_value = []
    browser_mgr = MagicMock(spec=BrowserManager)
    browser_mgr.get_session_info.return_value = None

    perm_mgr = MagicMock(spec=PermissionManager)
    gui_conf = GuiConfirmationProvider()

    agent = MagicMock(spec=Agent)
    agent.client = client
    agent.conversation = conv
    agent.registry = MagicMock()
    agent.registry.list.return_value = []

    controller = AssistantController(
        agent=agent,
        conversation_manager=conv_mgr,
        memory_manager=mem_mgr,
        knowledge_manager=know_mgr,
        browser_manager=browser_mgr,
        permission_manager=perm_mgr,
        gui_confirmation=gui_conf,
        voice_manager=voice_manager,
        settings=settings,
    )

    window = MainWindow(controller=controller, voice_controller=voice_controller)
    return window, voice_controller, controller


def test_voice_integration_full_flow(voice_gui_fixture, qapp: QApplication) -> None:
    window, voice_controller, controller = voice_gui_fixture

    # 1. Verify mic button is enabled and ready
    assert window.input_bar.mic_btn.isEnabled()
    assert window.input_bar.mic_btn.text() == "🎤"
    assert "Ready" in window.status_bar.voice_label.text()


    # 2. Click mic button to start recording
    window.input_bar.mic_btn.click()
    qapp.processEvents()
    assert voice_controller.is_recording()
    assert window.input_bar.mic_btn.text() == "🔴"
    assert "Recording" in window.status_bar.voice_label.text()

    # 3. Click mic button again to stop recording and trigger transcription
    window.input_bar.mic_btn.click()
    qapp.processEvents()
    assert voice_controller.is_transcribing() or voice_controller.current_state == VoiceState.TRANSCRIBING

    # 4. Wait for background worker to complete
    if voice_controller._active_worker:
        voice_controller._active_worker.wait(3000)
    qapp.processEvents()


    # 5. Transcription must appear in the input box for user review
    prompt_content = window.input_bar.text_input.toPlainText()
    assert prompt_content == "What is the system uptime?"

    # 6. Verify prompt was NOT sent automatically (assistant must not have started turn)
    assert controller.current_state.value == "idle"

    # 7. User can edit the transcript before sending
    window.input_bar.text_input.setPlainText("What is the system uptime and CPU usage?")
    assert window.input_bar.text_input.toPlainText() == "What is the system uptime and CPU usage?"

    # 8. User clicks Send explicitly
    with patch.object(controller, "send_message") as mock_send:
        window.input_bar.send_btn.click()
        mock_send.assert_called_once_with("What is the system uptime and CPU usage?")

    window.close()
