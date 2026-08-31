"""End-to-end integration tests for Text-to-Speech manual and auto-speak workflows."""

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
from app.ui.tts_controller import TTSController
from app.ui.voice_controller import VoiceController
from app.voice.manager import VoiceManager
from app.voice.providers import MockSpeechToTextProvider
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
def tts_gui_fixture(tmp_path: Path, qapp: QApplication):
    settings = Settings(voice_enabled=True, tts_enabled=True, auto_speak_responses=False)

    stt = MockSpeechToTextProvider()
    stt_recorder = MagicMock()
    voice_manager = VoiceManager(settings=settings, stt_provider=stt, recorder=stt_recorder)
    voice_controller = VoiceController(voice_manager=voice_manager, settings=settings)

    tts_provider = MockTTSProvider()
    tts_player = MagicMock()
    tts_manager = TTSManager(settings=settings, provider=tts_provider, player=tts_player)
    tts_controller = TTSController(tts_manager=tts_manager, settings=settings)

    client = MagicMock(spec=OllamaClient)
    client.default_model = "llama3"
    client.get_status.return_value = MagicMock(
        is_connected=True,
        base_url="http://localhost:11434",
        is_model_available=True,
        available_models=["llama3"],
    )

    conv_mgr = MagicMock(spec=ConversationManager)
    conv = Conversation(conversation_id="conv-tts")
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
        tts_manager=tts_manager,
        settings=settings,
    )

    window = MainWindow(
        controller=controller,
        voice_controller=voice_controller,
        tts_controller=tts_controller,
    )
    return window, tts_controller, controller


def test_tts_manual_speak_flow(tts_gui_fixture, qapp: QApplication) -> None:
    window, tts_controller, controller = tts_gui_fixture

    # 1. Create an assistant message bubble
    bubble = window.chat_view.start_assistant_message()
    bubble.set_content("The current CPU usage is **15%**.")

    # 2. Verify speak button exists on assistant bubble
    assert hasattr(bubble, "speak_btn")
    assert bubble.speak_btn.text() == "🔊"

    # 3. User clicks manual speak button
    bubble.speak_btn.click()
    qapp.processEvents()

    assert tts_controller.is_speaking() or tts_controller.current_state in (TTSState.SPEAKING, TTSState.IDLE)

    if tts_controller._active_worker:
        tts_controller._active_worker.wait(3000)
    qapp.processEvents()

    assert tts_controller.current_state == TTSState.IDLE
    window.close()


def test_tts_auto_speak_flow(tts_gui_fixture, qapp: QApplication) -> None:
    window, tts_controller, controller = tts_gui_fixture

    # 1. Enable auto-speak
    tts_controller.settings.auto_speak_responses = True

    # 2. Simulate turn completed
    window._on_turn_completed("Calculation completed: 25 * 4 = 100.")
    qapp.processEvents()

    assert tts_controller.is_speaking() or tts_controller.current_state in (TTSState.SPEAKING, TTSState.IDLE)

    if tts_controller._active_worker:
        tts_controller._active_worker.wait(3000)
    qapp.processEvents()

    assert tts_controller.current_state == TTSState.IDLE
    window.close()
