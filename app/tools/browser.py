"""Browser automation tools integrated with ToolRegistry and PermissionManager."""

from typing import TYPE_CHECKING, Any, Optional
from pydantic import BaseModel, Field, field_validator

from app.core.config import Settings, get_settings
from app.tools.base import RiskLevel, Tool, ToolResult

if TYPE_CHECKING:
    from app.browser.manager import BrowserManager


# --- Input Schemas ---

class BrowserOpenArgs(BaseModel):
    """Arguments for opening a webpage."""

    url: str = Field(description="The HTTP or HTTPS website URL to navigate to (e.g. 'https://github.com')")


class BrowserSearchArgs(BaseModel):
    """Arguments for web search."""

    query: str = Field(description="Keywords or phrase to search for on the web")


class BrowserEmptyArgs(BaseModel):
    """Empty argument schema for parameterless browser tools."""


class BrowserClickArgs(BaseModel):
    """Arguments for clicking a page element."""

    element_id: int = Field(ge=1, description="The integer ID of the element to click (from page snapshot elements, e.g. 1, 2, 3)")


class BrowserTypeArgs(BaseModel):
    """Arguments for typing text into an input element."""

    element_id: int = Field(ge=1, description="The integer ID of the input element (from page snapshot elements, e.g. 1, 2, 3)")
    text: str = Field(description="The text content to enter into the targeted input field")


class BrowserScrollArgs(BaseModel):
    """Arguments for scrolling the page view."""

    direction: Optional[str] = Field(default="down", description="Scroll direction: 'down' or 'up' (default 'down')")
    amount: Optional[int] = Field(default=500, ge=50, le=5000, description="Amount of pixels to scroll (default 500)")

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: Optional[str]) -> str:
        if v is None:
            return "down"
        cleaned = v.strip().lower()
        if cleaned not in ("up", "down"):
            raise ValueError(f"Invalid scroll direction '{v}'. Must be 'up' or 'down'.")
        return cleaned



# --- Base Browser Tool ---

class BaseBrowserTool(Tool):
    """Base class for all browser automation tools."""

    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        args_model: Optional[type[BaseModel]] = None,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(name=name, description=description, risk_level=risk_level, args_model=args_model)
        self.settings = settings or get_settings()
        if browser_manager is None:
            from app.browser.manager import BrowserManager

            self.browser_manager = BrowserManager(settings=self.settings)
        else:
            self.browser_manager = browser_manager


# --- Browser Tool Implementations ---

class BrowserOpenTool(BaseBrowserTool):
    """Tool to open a website URL in the browser."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_open",
            description="Open a website URL in the browser and retrieve the page title and initial content.",
            risk_level=RiskLevel.LOW,
            args_model=BrowserOpenArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        url = args["url"]
        nav_res, page_state, wrapped_context = self.browser_manager.open_url(url)
        return ToolResult(
            success=nav_res.success,
            data={
                "url": page_state.url,
                "title": page_state.title,
                "status_code": nav_res.status_code,
                "elements_count": len(page_state.elements),
                "context_text": wrapped_context,
            },
            message=f"Opened '{page_state.title}' ({page_state.url})",
        )


class BrowserSearchTool(BaseBrowserTool):
    """Tool to perform a privacy-friendly web search."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_search",
            description="Perform a web search through the browser and retrieve search results and page text.",
            risk_level=RiskLevel.LOW,
            args_model=BrowserSearchArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        query = args["query"]
        nav_res, page_state, wrapped_context = self.browser_manager.search(query)
        return ToolResult(
            success=nav_res.success,
            data={
                "query": query,
                "url": page_state.url,
                "title": page_state.title,
                "context_text": wrapped_context,
            },
            message=f"Search completed for '{query}'. Current page: '{page_state.title}'",
        )


class BrowserGetPageTool(BaseBrowserTool):
    """Tool to retrieve bounded text and interactive elements of the current page."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_get_page",
            description="Retrieve the bounded text content and interactive elements list for the current active webpage.",
            risk_level=RiskLevel.READ,
            args_model=BrowserEmptyArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        page_state, wrapped_context = self.browser_manager.get_current_page()
        return ToolResult(
            success=True,
            data={
                "url": page_state.url,
                "title": page_state.title,
                "elements_count": len(page_state.elements),
                "context_text": wrapped_context,
            },
            message=f"Retrieved content for '{page_state.title}' ({len(page_state.elements)} interactive elements)",
        )


class BrowserCurrentPageTool(BaseBrowserTool):
    """Tool to check current URL and title without re-fetching entire DOM."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_current_page",
            description="Return the current URL, title, and session status of the active browser window.",
            risk_level=RiskLevel.READ,
            args_model=BrowserEmptyArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        session = self.browser_manager.get_session_info()
        curr_state = self.browser_manager._current_page_state
        url = curr_state.url if curr_state else (session.current_url if session else "No page loaded")
        title = curr_state.title if curr_state else (session.current_title if session else "")

        return ToolResult(
            success=True,
            data={
                "session_id": session.session_id if session else None,
                "url": url,
                "title": title,
                "is_active": session.is_active if session else False,
            },
            message=f"Current browser page: '{title}' ({url})",
        )


class BrowserClickTool(BaseBrowserTool):
    """Tool to click an identified interactive element on the page."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_click",
            description="Click an element on the current webpage by its integer ID [#X] from the page elements list. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=BrowserClickArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        element_id = args["element_id"]
        action_res = self.browser_manager.click_element(element_id)
        return ToolResult(
            success=action_res.success,
            data=action_res.model_dump(),
            message=action_res.message,
            error=action_res.error,
        )


class BrowserTypeTool(BaseBrowserTool):
    """Tool to type text into an input field on the page."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_type",
            description="Enter text into an identified input element [#X] on the current webpage. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=BrowserTypeArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        element_id = args["element_id"]
        text = args["text"]
        action_res = self.browser_manager.type_element(element_id, text)
        return ToolResult(
            success=action_res.success,
            data=action_res.model_dump(),
            message=action_res.message,
            error=action_res.error,
        )


class BrowserScrollTool(BaseBrowserTool):
    """Tool to scroll the page view."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_scroll",
            description="Scroll the current webpage up or down by a specified pixel amount.",
            risk_level=RiskLevel.LOW,
            args_model=BrowserScrollArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        direction = args.get("direction", "down")
        amount = args.get("amount", 500)
        action_res = self.browser_manager.scroll(direction=direction, amount=amount)
        return ToolResult(
            success=action_res.success,
            data=action_res.model_dump(),
            message=action_res.message,
            error=action_res.error,
        )


class BrowserBackTool(BaseBrowserTool):
    """Tool to navigate back in browser history."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_back",
            description="Navigate backward to the previous page in browsing history.",
            risk_level=RiskLevel.LOW,
            args_model=BrowserEmptyArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        action_res = self.browser_manager.back()
        return ToolResult(
            success=action_res.success,
            data=action_res.model_dump(),
            message=action_res.message,
            error=action_res.error,
        )


class BrowserForwardTool(BaseBrowserTool):
    """Tool to navigate forward in browser history."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_forward",
            description="Navigate forward to the next page in browsing history.",
            risk_level=RiskLevel.LOW,
            args_model=BrowserEmptyArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        action_res = self.browser_manager.forward()
        return ToolResult(
            success=action_res.success,
            data=action_res.model_dump(),
            message=action_res.message,
            error=action_res.error,
        )


class BrowserCloseTool(BaseBrowserTool):
    """Tool to close the active browser session."""

    def __init__(
        self,
        browser_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="browser_close",
            description="Close the active browser session and release memory and system resources.",
            risk_level=RiskLevel.LOW,
            args_model=BrowserEmptyArgs,
            browser_manager=browser_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        closed = self.browser_manager.close_session()
        return ToolResult(
            success=closed,
            data={"closed": closed},
            message="Browser session closed successfully.",
        )
