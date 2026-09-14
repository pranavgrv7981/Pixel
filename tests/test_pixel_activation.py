"""Unit and integration tests for Pixel Activation and Global Assistant Summoning."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import pytest

from app.agent.agent import Agent
from app.core.config import Settings
from app.core.single_instance import SingleInstanceManager
from app.ui.hotkey import GlobalHotkeyManager, parse_hotkey_string
from app.ui.main_window import MainWindow
from app.agent.conversation import Conversation, ConversationManager
from app.browser import BrowserManager
from app.core.ollama_client import OllamaClient
from app.knowledge import KnowledgeManager
from app.memory import MemoryManager
from app.security.manager import PermissionManager
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.controller import AssistantController
from app.ui.models import UIState
from app.ui.tray import AssistantTrayIcon
from app.voice.models import TranscriptionResult
from app.voice.providers import SpeechToTextProvider
from app.voice.wake import VoiceWakeDetector, WakePhraseValidator


@pytest.fixture
def window(qapp: QApplication) -> MainWindow:
    settings = Settings()
    client = MagicMock(spec=OllamaClient)
    client.default_model = "llama3"
    client.get_status.return_value = MagicMock(
        is_connected=True,
        base_url="http://localhost:11434",
        is_model_available=True,
        available_models=["llama3"],
    )

    conv_mgr = MagicMock(spec=ConversationManager)
    conv = Conversation(conversation_id="conv-test")
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
        settings=settings,
    )
    return MainWindow(controller=controller)


# ----------------------------------------------------------------------
# 1. Hotkey Parsing and Registration Tests
# ----------------------------------------------------------------------

def test_hotkey_string_parsing():
    """Verify parsing of Alt+P, Ctrl+Alt+P, and other shortcut combos."""
    mods, vk = parse_hotkey_string("Alt+P")
    assert vk == ord("P")
    assert mods & 0x0001 != 0  # MOD_ALT

    mods_c, vk_c = parse_hotkey_string("Ctrl+Alt+Space")
    assert vk_c == 0x20
    assert mods_c & 0x0001 != 0  # MOD_ALT
    assert mods_c & 0x0002 != 0  # MOD_CONTROL


def test_hotkey_manager_lifecycle():
    """Verify start, stop, and clean unregistration of GlobalHotkeyManager."""
    triggered = []
    mgr = GlobalHotkeyManager(hotkey_str="Ctrl+Shift+F11", on_trigger=lambda: triggered.append(True))
    res = mgr.start()
    assert res is True
    assert mgr.is_registered is True

    # Trigger signal
    mgr.hotkey_triggered.emit()
    assert len(triggered) == 1

    # Stop and unregister
    mgr.stop()
    assert mgr.is_registered is False

    # Re-registration after stop
    res2 = mgr.start()
    assert res2 is True
    assert mgr.is_registered is True
    mgr.stop()


# ----------------------------------------------------------------------
# 2. Window Summoning and Focus Tests
# ----------------------------------------------------------------------

def test_summon_pixel_while_hidden(window: MainWindow, qapp: QApplication):
    """Verify summon_pixel restores a hidden window and focuses text input."""
    window.hide()
    assert window.isHidden()

    window.summon_pixel("hotkey")
    qapp.processEvents()

    assert not window.isHidden()
    assert window.isVisible()
    assert window.input_bar.text_input.hasFocus()


def test_summon_pixel_while_minimized(window: MainWindow, qapp: QApplication):
    """Verify summon_pixel restores a minimized window to normal geometry."""
    window.showMinimized()
    qapp.processEvents()

    window.summon_pixel("hotkey")
    qapp.processEvents()

    assert not window.isMinimized()
    assert window.isVisible()
    assert window.input_bar.text_input.hasFocus()


def test_summon_pixel_repeated(window: MainWindow, qapp: QApplication):
    """Verify repeated summon_pixel keeps input focus and does not disrupt state."""
    window.summon_pixel("hotkey")
    qapp.processEvents()
    assert window.input_bar.text_input.hasFocus()

    window.input_bar.text_input.setPlainText("Hello Pixel")
    window.summon_pixel("hotkey")
    qapp.processEvents()

    assert window.input_bar.text_input.hasFocus()
    assert window.input_bar.text_input.toPlainText() == "Hello Pixel"


def test_summon_pixel_zero_model_overhead(window: MainWindow, qapp: QApplication):
    """Verify summoning Pixel does NOT invoke Ollama or model inference."""
    with patch.object(window.controller.agent, "stream_run") as mock_stream:
        window.summon_pixel("hotkey")
        qapp.processEvents()
        mock_stream.assert_not_called()


def test_summon_pixel_while_worker_busy(window: MainWindow, qapp: QApplication):
    """Verify summoning Pixel while inference is busy focuses UI without crashing or cancelling."""
    window.controller.set_state(UIState.STREAMING)
    window.summon_pixel("hotkey")
    qapp.processEvents()

    assert window.isVisible()
    assert window.controller.current_state == UIState.STREAMING
    window.controller.set_state(UIState.IDLE)


# ----------------------------------------------------------------------
# 3. Voice Wake Recognition and False-Wake Protection
# ----------------------------------------------------------------------

def test_wake_phrase_validator_valid_commands():
    """Verify strict validation of authentic Pixel wake commands."""
    assert WakePhraseValidator.is_wake_command("Pixel, open")
    assert WakePhraseValidator.is_wake_command("Pixel open")
    assert WakePhraseValidator.is_wake_command("PIXEL OPEN")
    assert WakePhraseValidator.is_wake_command("Open Pixel")
    assert WakePhraseValidator.is_wake_command("  open   pixel  ! ")
    assert WakePhraseValidator.is_wake_command("Hey Pixel")
    assert WakePhraseValidator.is_wake_command("Hey Pixel, open")
    assert WakePhraseValidator.is_wake_command("Hi Pixel open")


def test_wake_phrase_validator_false_wakes_rejected():
    """Verify rejection of non-summon conversation containing 'pixel'."""
    assert not WakePhraseValidator.is_wake_command("My pixel display is broken.")
    assert not WakePhraseValidator.is_wake_command("I use pixels in my image.")
    assert not WakePhraseValidator.is_wake_command("Can you fix the dead pixels on my screen?")
    assert not WakePhraseValidator.is_wake_command("The Google Pixel 9 camera is good.")
    assert not WakePhraseValidator.is_wake_command("Let's buy a pixel art drawing.")
    assert not WakePhraseValidator.is_wake_command("What is the resolution in pixels?")
    assert not WakePhraseValidator.is_wake_command("Hello world")
    assert not WakePhraseValidator.is_wake_command("")


def test_voice_wake_detector_disabled_by_default():
    """Verify voice wake detector does not start listener when disabled."""
    cfg = Settings(voice_wake_enabled=False)
    mock_stt = MagicMock(spec=SpeechToTextProvider)
    detector = VoiceWakeDetector(settings=cfg, stt_provider=mock_stt)

    assert detector.is_enabled is False
    res = detector.start()
    assert res is False
    assert detector.is_running is False


def test_voice_wake_detector_toggle_and_candidate_processing():
    """Verify voice wake candidate audio processing triggers wake_detected signal."""
    cfg = Settings(voice_wake_enabled=True)
    mock_stt = MagicMock(spec=SpeechToTextProvider)
    mock_stt.transcribe.return_value = TranscriptionResult(
        text="Pixel, open",
        language="en",
        duration=1.5,
        confidence=0.95,
    )

    detected_events = []
    detector = VoiceWakeDetector(
        settings=cfg,
        stt_provider=mock_stt,
        on_wake=detected_events.append,
    )

    # Process simulated audio buffer
    import numpy as np
    dummy_audio = np.zeros(16000 * 2, dtype=np.float32)
    detector._process_candidate_audio(dummy_audio)

    assert len(detected_events) == 1
    assert detected_events[0] == "Pixel, open"


# ----------------------------------------------------------------------
# 4. Single Instance and Tray Integration
# ----------------------------------------------------------------------

def test_single_instance_summon_dispatch(window: MainWindow, qapp: QApplication):
    """Verify single instance activation invokes summon_pixel."""
    woken = []
    simulated_mgr = SingleInstanceManager(on_activate=lambda: window.summon_pixel("single_instance"))

    # Simulate secondary process notifying primary
    if simulated_mgr.on_activate:
        simulated_mgr.on_activate()
    qapp.processEvents()

    assert window.isVisible()
    assert window.input_bar.text_input.hasFocus()


def test_tray_menu_actions(window: MainWindow, qapp: QApplication):
    """Verify Pixel tray menu contains required summon and toggle items."""
    tray = AssistantTrayIcon(
        main_window=window,
        voice_wake_toggle_callback=lambda enabled: None,
        new_chat_callback=window.controller.new_conversation,
    )

    assert tray.open_action.text() == "Open Pixel"
    assert tray.new_chat_action.text() == "New Chat"
    assert tray.voice_wake_action.text() == "Voice Wake"
    assert tray.pause_action.text() == "Pause Background Activity"
    assert tray.quit_action.text() == "Exit Pixel"

    # Test open action restores window
    window.hide()
    tray.open_action.trigger()
    qapp.processEvents()
    assert window.isVisible()


def test_summon_latency_under_300ms(window: MainWindow, qapp: QApplication):
    """Verify window summoning and focus executes well under 300 ms target."""
    window.hide()
    qapp.processEvents()

    t_start = time.perf_counter()
    window.summon_pixel("hotkey")
    qapp.processEvents()
    elapsed = time.perf_counter() - t_start

    assert elapsed < 0.300  # under 300ms
    assert window.isVisible()


def test_voice_wake_feedback_tts_gating(window: MainWindow, qapp: QApplication):
    """Verify local TTS 'Ready.' is triggered upon voice summon without LLM call."""
    mock_tts = MagicMock()
    window.tts_controller = mock_tts

    # Summon via voice
    window.summon_pixel("voice")
    qapp.processEvents()

    mock_tts.speak_text.assert_called_once_with("Ready.", interrupt_current=True)


def test_voice_wake_detector_enable_disable_lifecycle():
    """Verify set_enabled toggles detector running state cleanly."""
    cfg = Settings(voice_wake_enabled=False)
    mock_stt = MagicMock(spec=SpeechToTextProvider)
    detector = VoiceWakeDetector(settings=cfg, stt_provider=mock_stt)

    assert detector.is_enabled is False
    assert detector.is_running is False

    detector.set_enabled(True)
    assert detector.is_enabled is True
    # Clean stop
    detector.set_enabled(False)
    assert detector.is_enabled is False
    assert detector.is_running is False
