"""Tests for the 10 browser tools schemas, risk levels, and execution."""

import pytest

from app.core.config import Settings
from app.core.exceptions import ToolValidationError
from app.browser.manager import BrowserManager
from app.browser.models import BrowserElement
from app.browser.provider import MockBrowserProvider
from app.tools.base import RiskLevel
from app.tools.browser import (
    BrowserBackTool,
    BrowserClickTool,
    BrowserCloseTool,
    BrowserCurrentPageTool,
    BrowserForwardTool,
    BrowserGetPageTool,
    BrowserOpenTool,
    BrowserScrollTool,
    BrowserSearchTool,
    BrowserTypeTool,
)


@pytest.fixture
def browser_tools() -> tuple[
    BrowserOpenTool,
    BrowserSearchTool,
    BrowserGetPageTool,
    BrowserCurrentPageTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserScrollTool,
    BrowserBackTool,
    BrowserForwardTool,
    BrowserCloseTool,
    MockBrowserProvider,
]:
    provider = MockBrowserProvider()
    settings = Settings()
    manager = BrowserManager(settings=settings, provider=provider)

    t_open = BrowserOpenTool(browser_manager=manager, settings=settings)
    t_search = BrowserSearchTool(browser_manager=manager, settings=settings)
    t_get_page = BrowserGetPageTool(browser_manager=manager, settings=settings)
    t_current = BrowserCurrentPageTool(browser_manager=manager, settings=settings)
    t_click = BrowserClickTool(browser_manager=manager, settings=settings)
    t_type = BrowserTypeTool(browser_manager=manager, settings=settings)
    t_scroll = BrowserScrollTool(browser_manager=manager, settings=settings)
    t_back = BrowserBackTool(browser_manager=manager, settings=settings)
    t_forward = BrowserForwardTool(browser_manager=manager, settings=settings)
    t_close = BrowserCloseTool(browser_manager=manager, settings=settings)

    return (
        t_open,
        t_search,
        t_get_page,
        t_current,
        t_click,
        t_type,
        t_scroll,
        t_back,
        t_forward,
        t_close,
        provider,
    )


def test_tool_risk_levels(browser_tools: tuple) -> None:
    (
        t_open,
        t_search,
        t_get_page,
        t_current,
        t_click,
        t_type,
        t_scroll,
        t_back,
        t_forward,
        t_close,
        _,
    ) = browser_tools

    assert t_get_page.risk_level == RiskLevel.READ
    assert t_current.risk_level == RiskLevel.READ

    assert t_open.risk_level == RiskLevel.LOW
    assert t_search.risk_level == RiskLevel.LOW
    assert t_scroll.risk_level == RiskLevel.LOW
    assert t_back.risk_level == RiskLevel.LOW
    assert t_forward.risk_level == RiskLevel.LOW
    assert t_close.risk_level == RiskLevel.LOW

    assert t_click.risk_level == RiskLevel.MEDIUM
    assert t_type.risk_level == RiskLevel.MEDIUM


def test_tool_executions(browser_tools: tuple) -> None:
    (
        t_open,
        t_search,
        t_get_page,
        t_current,
        t_click,
        t_type,
        t_scroll,
        t_back,
        t_forward,
        t_close,
        provider,
    ) = browser_tools

    provider.set_mock_page(
        url="https://example.com",
        title="Example Domain",
        text="Example Domain text for illustrative examples.",
        elements=[
            BrowserElement(element_id=1, tag="a", text="More information", selector="a >> nth=0"),
            BrowserElement(element_id=2, tag="input", element_type="text", name="q", selector="input >> nth=0"),
        ],
    )

    # 1. browser_open
    res_open = t_open.execute({"url": "https://example.com"})
    assert res_open.success is True
    assert res_open.data["title"] == "Example Domain"
    assert "=== UNTRUSTED WEB PAGE CONTENT ===" in res_open.data["context_text"]

    # 2. browser_current_page
    res_curr = t_current.execute({})
    assert res_curr.success is True
    assert res_curr.data["url"] == "https://example.com"

    # 3. browser_get_page
    res_get = t_get_page.execute({})
    assert res_get.success is True
    assert res_get.data["elements_count"] == 2

    # 4. browser_click
    res_click = t_click.execute({"element_id": 1})
    assert res_click.success is True
    assert res_click.data["target_element_id"] == 1

    # 5. browser_type
    res_type = t_type.execute({"element_id": 2, "text": "hello world"})
    assert res_type.success is True

    # 6. browser_scroll
    res_scroll = t_scroll.execute({"direction": "down", "amount": 300})
    assert res_scroll.success is True

    # 7. browser_back & forward
    res_back = t_back.execute({})
    assert res_back.success is True
    res_fwd = t_forward.execute({})
    assert res_fwd.success is True

    # 8. browser_close
    res_close = t_close.execute({})
    assert res_close.success is True
    assert res_close.data["closed"] is True


def test_tool_argument_validation(browser_tools: tuple) -> None:
    t_open, t_search, _, _, t_click, t_type, t_scroll, _, _, _, _ = browser_tools

    # Missing url
    with pytest.raises(ToolValidationError):
        t_open.validate_args({})

    # Missing query
    with pytest.raises(ToolValidationError):
        t_search.validate_args({})

    # Missing element_id
    with pytest.raises(ToolValidationError):
        t_click.validate_args({})

    # Negative element_id
    with pytest.raises(ToolValidationError):
        t_click.validate_args({"element_id": 0})

    # Missing text for typing
    with pytest.raises(ToolValidationError):
        t_type.validate_args({"element_id": 1})

    # Invalid scroll direction
    with pytest.raises(ToolValidationError):
        t_scroll.validate_args({"direction": "sideways"})

