"""Unit tests for MainWindow layout, widget tree, and UI interactions."""

import os
import sys
from unittest.mock import MagicMock
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

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


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

    win = MainWindow(controller=controller)
    return win


def test_main_window_subwidgets_exist(window: MainWindow) -> None:
    assert window.sidebar is not None
    assert window.chat_view is not None
    assert window.input_bar is not None
    assert window.status_bar is not None
    assert "Local AI Personal Assistant" in window.windowTitle()


def test_chat_view_message_rendering(window: MainWindow) -> None:
    user_bubble = window.chat_view.add_user_message("Hello from test user")
    assert user_bubble is not None
    assert "Hello from test user" in user_bubble.get_content()

    asst_bubble = window.chat_view.start_assistant_message()
    assert asst_bubble is not None
    assert asst_bubble._is_thinking is True

    window.chat_view.append_assistant_chunk("Hello! ")
    assert asst_bubble._is_thinking is False
    window.chat_view.append_assistant_chunk("How can I assist?")
    assert asst_bubble.get_content() == "Hello! How can I assist?"


def test_chat_view_error_rendering(window: MainWindow) -> None:
    asst_bubble = window.chat_view.start_assistant_message()
    window.chat_view.mark_assistant_error("Model server connection timed out.")
    assert "Unable to generate a response" in asst_bubble.get_content()
    assert "Model server connection timed out." in asst_bubble.get_content()


def test_chat_view_cancellation(window: MainWindow) -> None:
    asst_bubble = window.chat_view.start_assistant_message()
    window.chat_view.cancel_assistant_message()
    assert "stopped by user" in asst_bubble.get_content()


def test_chat_view_tool_activity(window: MainWindow) -> None:
    tool_widget = window.chat_view.add_tool_activity("get_system_info", {})
    assert tool_widget.tool_name == "get_system_info"
    assert tool_widget.status_label.text() == "Executing..."

    window.chat_view.finish_tool_activity("get_system_info", True, "RAM: 16 GB")
    assert tool_widget.status_label.text() == "Completed"


def test_main_window_clean_shutdown(window: MainWindow) -> None:
    window.close()
    assert not window.status_timer.isActive()


def test_turn_completed_empty_response_handling(window: MainWindow) -> None:
    asst_bubble = window.chat_view.start_assistant_message()
    window._on_turn_completed("")
    assert "No response" in asst_bubble.get_content()

