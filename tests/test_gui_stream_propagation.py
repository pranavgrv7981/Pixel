"""Regression tests verifying token propagation from AssistantController to ChatView."""

import time
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
import pytest
from app.agent.agent import Agent
from app.agent.conversation import Conversation, ConversationManager
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.controller import AssistantController
from app.ui.widgets.chat_view import ChatView


def test_controller_stream_propagation_to_chat_view(qapp: QApplication):
    """Verify streamed tokens from controller append to active assistant message bubble."""
    settings = Settings()
    client = MagicMock(spec=OllamaClient)
    client.default_model = "qwen3:30b"

    agent = MagicMock(spec=Agent)
    agent.client = client
    agent.conversation = Conversation()
    agent.stream_run.return_value = ["Hi", " there", "!"]

    conv_mgr = MagicMock(spec=ConversationManager)
    gui_conf = GuiConfirmationProvider()

    controller = AssistantController(
        agent=agent,
        conversation_manager=conv_mgr,
        memory_manager=MagicMock(),
        knowledge_manager=MagicMock(),
        browser_manager=MagicMock(),
        permission_manager=MagicMock(),
        gui_confirmation=gui_conf,
        settings=settings,
    )

    chat_view = ChatView()
    controller.chunk_received.connect(chat_view.append_assistant_chunk)

    # Simulate user sending message
    chat_view.add_user_message("hi")
    chat_view.start_assistant_message()

    controller.send_message("hi")
    start_t = time.time()
    while controller._active_worker and controller._active_worker.isRunning() and (time.time() - start_t) < 5.0:
        qapp.processEvents()
        time.sleep(0.01)

    qapp.processEvents()

    bubble = chat_view._current_assistant_bubble
    assert bubble is not None
    assert bubble.get_content() == "Hi there!"
    assert not bubble._is_thinking
