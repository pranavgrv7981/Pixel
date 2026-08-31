"""Tests for BrowserManager session management, lazy startup, navigation, and element interaction."""

from datetime import datetime, timedelta, timezone
import pytest

from app.core.config import Settings
from app.core.exceptions import ToolExecutionError, ToolValidationError
from app.browser.manager import BrowserManager
from app.browser.models import BrowserElement
from app.browser.provider import MockBrowserProvider
from app.browser.security import URLValidator


@pytest.fixture
def mock_browser_manager() -> tuple[BrowserManager, MockBrowserProvider]:
    provider = MockBrowserProvider()
    settings = Settings(
        browser_session_timeout_seconds=300.0,
        browser_page_timeout_seconds=10.0,
        browser_action_timeout_seconds=5.0,
    )
    validator = URLValidator(allow_local_network=False)
    manager = BrowserManager(settings=settings, provider=provider, validator=validator)
    return manager, provider


def test_lazy_session_initialization_on_open(mock_browser_manager: tuple[BrowserManager, MockBrowserProvider]) -> None:
    manager, provider = mock_browser_manager
    assert manager.get_session_info() is None
    assert provider.is_running() is False

    nav_res, state, wrapped = manager.open_url("https://example.com")

    assert nav_res.success is True
    assert provider.is_running() is True
    assert manager.get_session_info() is not None
    assert manager.get_session_info().is_active is True
    assert manager.get_session_info().navigation_count == 1
    assert "https://example.com" in state.url
    assert "=== UNTRUSTED WEB PAGE CONTENT ===" in wrapped


def test_session_recycling_on_idle_timeout(mock_browser_manager: tuple[BrowserManager, MockBrowserProvider]) -> None:
    manager, provider = mock_browser_manager
    manager.open_url("https://example.com")
    first_session_id = manager.get_session_info().session_id

    # Artificially age session beyond timeout (300s)
    manager._session_info.last_active_at = datetime.now(timezone.utc) - timedelta(seconds=350)

    # Next action triggers session recycling
    manager.open_url("https://python.org")
    new_session_id = manager.get_session_info().session_id

    assert new_session_id != first_session_id
    assert manager.get_session_info().navigation_count == 1


def test_click_element_valid_and_invalid(mock_browser_manager: tuple[BrowserManager, MockBrowserProvider]) -> None:
    manager, provider = mock_browser_manager
    provider.set_mock_page(
        url="https://example.com/form",
        title="Form",
        text="Please enter details",
        elements=[
            BrowserElement(element_id=1, tag="input", element_type="text", name="username", selector="input >> nth=0"),
            BrowserElement(element_id=2, tag="button", text="Submit", selector="button >> nth=0"),
        ],
    )
    manager.open_url("https://example.com/form")

    # Valid click on button [#2]
    res_click = manager.click_element(2)
    assert res_click.success is True
    assert "Clicked element [#" in res_click.message

    # Invalid click on non-existent element [#99]
    with pytest.raises(ToolValidationError) as exc_info:
        manager.click_element(99)
    assert "invalid or stale" in str(exc_info.value).lower()


def test_type_element(mock_browser_manager: tuple[BrowserManager, MockBrowserProvider]) -> None:
    manager, provider = mock_browser_manager
    provider.set_mock_page(
        url="https://example.com/login",
        title="Login",
        text="Login Page",
        elements=[
            BrowserElement(element_id=1, tag="input", element_type="text", name="user", selector="input >> nth=0"),
        ],
    )
    manager.open_url("https://example.com/login")

    res_type = manager.type_element(1, "my_username")
    assert res_type.success is True
    assert "my_username" in res_type.message


def test_search_url_construction(mock_browser_manager: tuple[BrowserManager, MockBrowserProvider]) -> None:
    manager, provider = mock_browser_manager
    nav_res, state, wrapped = manager.search("python asyncio documentation")
    assert nav_res.success is True
    assert "duckduckgo" in state.url
    assert "python+asyncio+documentation" in state.url or "python" in state.url


def test_close_session_cleanup(mock_browser_manager: tuple[BrowserManager, MockBrowserProvider]) -> None:
    manager, provider = mock_browser_manager
    manager.open_url("https://example.com")
    assert provider.is_running() is True

    closed = manager.close_session()
    assert closed is True
    assert provider.is_running() is False
    assert manager.get_session_info().is_active is False
