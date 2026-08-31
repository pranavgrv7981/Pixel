"""Tests for browser data models and element serialization."""

from datetime import datetime, timezone
import pytest

from app.browser.models import (
    BrowserActionResult,
    BrowserElement,
    BrowserSessionInfo,
    NavigationResult,
    PageState,
)


def test_browser_element_properties() -> None:
    el = BrowserElement(
        element_id=1,
        tag="button",
        text="Submit Order",
        element_type="submit",
        name="btn_submit",
        selector="button >> nth=0",
    )
    assert el.element_id == 1
    assert el.tag == "button"
    assert el.is_interactive is True
    assert el.is_sensitive is False

    pwd = BrowserElement(
        element_id=2,
        tag="input",
        element_type="password",
        selector="input[type='password']",
        is_sensitive=True,
    )
    assert pwd.is_sensitive is True


def test_page_state_element_lookup_and_formatting() -> None:
    el1 = BrowserElement(element_id=1, tag="a", text="Documentation", selector="a >> nth=0")
    el2 = BrowserElement(element_id=2, tag="input", element_type="text", placeholder="Search docs...", selector="input >> nth=0")
    el3 = BrowserElement(element_id=3, tag="button", text="Search", selector="button >> nth=0")

    state = PageState(
        url="https://example.com/docs",
        title="Documentation - Example",
        text_content="Welcome to the developer documentation.",
        elements=[el1, el2, el3],
    )

    assert state.get_element(1) == el1
    assert state.get_element(2) == el2
    assert state.get_element(99) is None

    summary = state.format_elements_summary()
    assert '[#1] [a] "Documentation"' in summary
    assert '[#2] [text] "Search docs..."' in summary
    assert '[#3] [button] "Search"' in summary


def test_session_info_and_action_result() -> None:
    now = datetime.now(timezone.utc)
    info = BrowserSessionInfo(
        session_id="session-123",
        is_active=True,
        headless=True,
        current_url="https://example.com",
        current_title="Example Domain",
        created_at=now,
        last_active_at=now,
        navigation_count=2,
    )
    assert info.session_id == "session-123"
    assert info.navigation_count == 2

    action = BrowserActionResult(
        success=True,
        action="click",
        target_element_id=1,
        current_url="https://example.com/clicked",
        current_title="Clicked Page",
        message="Successfully clicked",
    )
    assert action.success is True
    assert action.target_element_id == 1
