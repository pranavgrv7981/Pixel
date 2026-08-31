"""Unit tests for AssistantController state coordination and worker management."""

import os
from unittest.mock import MagicMock, patch
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation, ConversationManager
from app.browser import BrowserManager
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.knowledge import KnowledgeManager
from app.memory import MemoryManager
from app.security.manager import PermissionManager
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.controller import AssistantController
from app.ui.models import UIState

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture
def mock_controller() -> AssistantController:
    settings = Settings()
    client = MagicMock(spec=OllamaClient)
    client.default_model = "llama3"
    client.base_url = "http://localhost:11434"
    client.get_status.return_value = MagicMock(
        is_connected=True,
        base_url="http://localhost:11434",
        is_model_available=True,
        available_models=["llama3", "qwen3:30b"],
    )

    conv_mgr = MagicMock(spec=ConversationManager)
    mock_conv = Conversation(conversation_id="conv-1")
    conv_mgr.create_conversation.return_value = mock_conv
    conv_mgr.load_conversation.return_value = mock_conv
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
    agent.conversation = mock_conv
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
    return controller


def test_controller_initial_state(mock_controller: AssistantController) -> None:
    assert mock_controller.current_state == UIState.IDLE
    assert mock_controller.selected_model == "llama3"


def test_controller_set_model(mock_controller: AssistantController) -> None:
    mock_controller.set_selected_model("qwen3:30b")
    assert mock_controller.selected_model == "qwen3:30b"
    assert mock_controller.agent.client.default_model == "qwen3:30b"


def test_controller_state_transition(mock_controller: AssistantController) -> None:
    received = []
    mock_controller.state_changed.connect(lambda s: received.append(s))

    mock_controller.set_state(UIState.THINKING)
    assert mock_controller.current_state == UIState.THINKING
    assert received == ["thinking"]


def test_controller_new_conversation(mock_controller: AssistantController) -> None:
    new_conv_events = []
    mock_controller.active_conversation_changed.connect(lambda cid, title, msgs: new_conv_events.append((cid, title)))

    mock_controller.new_conversation()
    assert len(new_conv_events) == 1
    assert new_conv_events[0][0] == "conv-1"


def test_controller_check_status(mock_controller: AssistantController) -> None:
    status = mock_controller.check_backend_status()
    assert status.ollama_connected is True
    assert "qwen3:30b" in status.available_models
