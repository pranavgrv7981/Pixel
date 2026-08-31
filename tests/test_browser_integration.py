"""Integration tests for browser tools with Agent, PermissionManager, and confirmations."""

from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import Settings
from app.core.ollama_client import ModelResponse, OllamaClient
from app.browser.manager import BrowserManager
from app.browser.models import BrowserElement
from app.browser.provider import MockBrowserProvider
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.manager import PermissionManager
from app.security.policies import SecurityPolicy
from app.tools.browser import (
    BrowserClickTool,
    BrowserGetPageTool,
    BrowserOpenTool,
    BrowserTypeTool,
)
from app.tools.registry import ToolRegistry


@pytest.fixture
def agent_browser_env() -> tuple[Agent, BrowserManager, MockBrowserProvider, MagicMock, MagicMock]:
    provider = MockBrowserProvider()
    provider.set_mock_page(
        url="https://example.com/portal",
        title="Portal",
        text="Welcome to the customer portal. Please click the button below.",
        elements=[
            BrowserElement(element_id=1, tag="button", text="Login", selector="button >> nth=0"),
            BrowserElement(element_id=2, tag="input", element_type="text", name="query", selector="input >> nth=0"),
        ],
    )
    settings = Settings()
    manager = BrowserManager(settings=settings, provider=provider)

    registry = ToolRegistry()
    registry.register(BrowserOpenTool(browser_manager=manager, settings=settings))
    registry.register(BrowserGetPageTool(browser_manager=manager, settings=settings))
    registry.register(BrowserClickTool(browser_manager=manager, settings=settings))
    registry.register(BrowserTypeTool(browser_manager=manager, settings=settings))

    mock_conf_provider = MagicMock(spec=ConfirmationProvider)
    conf_mgr = ConfirmationManager(provider=mock_conf_provider)
    perm_mgr = PermissionManager(policy=SecurityPolicy(), confirmation_manager=conf_mgr)

    mock_client = MagicMock(spec=OllamaClient)
    mock_client.base_url = "http://localhost:11434"
    mock_client.default_model = "llama3"
    mock_client.check_connection.return_value = True
    mock_client.model_exists.return_value = True

    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=mock_client,
        registry=registry,
        permission_manager=perm_mgr,
        settings=settings,
    )

    return agent, manager, provider, mock_client, mock_conf_provider


def test_agent_browser_open_auto_approved(agent_browser_env: tuple) -> None:
    agent, manager, provider, mock_client, mock_conf_provider = agent_browser_env

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "browser_open",
            "arguments": {"url": "https://example.com/portal"},
        }]),
        ModelResponse("The portal page welcomes you and asks to click the login button."),
    ]

    reply = agent.run("Open the portal webpage and tell me what it says.")

    assert "portal" in reply.lower()
    assert mock_client.chat.call_count == 2
    # LOW risk tool should be auto-approved without prompting user confirmation
    assert mock_conf_provider.request_confirmation.call_count == 0


def test_agent_browser_click_confirmed_by_user(agent_browser_env: tuple) -> None:
    agent, manager, provider, mock_client, mock_conf_provider = agent_browser_env
    # Open page first so elements are active
    manager.open_url("https://example.com/portal")

    # User approves confirmation
    mock_conf_provider.request_confirmation.return_value = True

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "browser_click",
            "arguments": {"element_id": 1},
        }]),
        ModelResponse("I clicked the Login button successfully."),
    ]

    reply = agent.run("Click the login button on the page.")

    assert "clicked" in reply.lower()
    assert mock_conf_provider.request_confirmation.call_count == 1
    assert "click(1)" in provider.actions_log


def test_agent_browser_click_declined_by_user(agent_browser_env: tuple) -> None:
    agent, manager, provider, mock_client, mock_conf_provider = agent_browser_env
    # Open page first so elements are active
    manager.open_url("https://example.com/portal")

    # User denies confirmation
    mock_conf_provider.request_confirmation.return_value = False

    mock_client.chat.side_effect = [
        ModelResponse("", tool_calls=[{
            "name": "browser_click",
            "arguments": {"element_id": 1},
        }]),
        ModelResponse("I could not click the button because permission was denied."),
    ]

    reply = agent.run("Click the login button.")

    assert "denied" in reply.lower() or "could not" in reply.lower()
    assert mock_conf_provider.request_confirmation.call_count == 1
    # Click should NOT have been performed on the provider!
    assert not any("click" in action for action in provider.actions_log)

