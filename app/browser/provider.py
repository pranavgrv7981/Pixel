"""Browser provider abstraction and Playwright implementation."""

from abc import ABC, abstractmethod
import re
from typing import Any, Optional

from app.core.exceptions import ToolExecutionError
from app.core.logging import get_logger
from app.browser.models import (
    BrowserActionResult,
    BrowserElement,
    NavigationResult,
    PageState,
)

logger = get_logger("browser.provider")


class BrowserProvider(ABC):
    """Abstract interface for browser automation drivers."""

    @abstractmethod
    def start(self, headless: bool = True) -> None:
        """Start the browser runtime session."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the browser runtime and release all resources."""

    @abstractmethod
    def is_running(self) -> bool:
        """Check if browser process and page are active."""

    @abstractmethod
    def navigate(self, url: str, timeout_seconds: float = 30.0) -> NavigationResult:
        """Navigate to a URL."""

    @abstractmethod
    def get_page_state(self, max_text_bytes: int = 32768, max_elements: int = 100) -> PageState:
        """Retrieve bounded page text content and interactive element snapshot."""

    @abstractmethod
    def click(self, element: BrowserElement, timeout_seconds: float = 15.0) -> BrowserActionResult:
        """Click an identified page element."""

    @abstractmethod
    def type(self, element: BrowserElement, text: str, timeout_seconds: float = 15.0) -> BrowserActionResult:
        """Type text into an identified input element."""

    @abstractmethod
    def scroll(self, direction: str = "down", amount: int = 500) -> BrowserActionResult:
        """Scroll the current page view."""

    @abstractmethod
    def go_back(self) -> BrowserActionResult:
        """Navigate back in browsing history."""

    @abstractmethod
    def go_forward(self) -> BrowserActionResult:
        """Navigate forward in browsing history."""


class PlaywrightBrowserProvider(BrowserProvider):
    """Production browser driver utilizing Playwright Chromium."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def start(self, headless: bool = True) -> None:
        """Launch Playwright Chromium instance."""
        if self.is_running():
            return

        try:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=headless,
                args=[
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--no-first-run",
                ],
            )
            # Create isolated browser context with file downloads disabled
            self._context = self._browser.new_context(
                accept_downloads=False,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            self._page = self._context.new_page()
            logger.info("Playwright Chromium browser started (headless=%s)", headless)
        except Exception as err:
            logger.exception("Failed to launch Playwright browser: %s", err)
            self.stop()
            raise ToolExecutionError(f"Failed to start browser automation: {err}") from err

    def stop(self) -> None:
        """Close page, context, browser, and playwright driver."""
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        finally:
            self._page = None

        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        finally:
            self._context = None

        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        finally:
            self._browser = None

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._playwright = None

        logger.info("Playwright browser stopped and resources released.")

    def is_running(self) -> bool:
        return self._browser is not None and self._page is not None and not self._page.is_closed()

    def navigate(self, url: str, timeout_seconds: float = 30.0) -> NavigationResult:
        if not self.is_running():
            self.start()

        timeout_ms = int(timeout_seconds * 1000)
        try:
            resp = self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            status = resp.status if resp else None
            title = self._page.title()
            current_url = self._page.url
            logger.info("Navigated to '%s' (status=%s, title='%s')", current_url, status, title)
            return NavigationResult(
                success=True,
                url=current_url,
                title=title,
                status_code=status,
            )
        except Exception as err:
            logger.error("Navigation to '%s' failed: %s", url, err)
            current_url = self._page.url if self._page else url
            return NavigationResult(
                success=False,
                url=current_url,
                error=f"Navigation failed: {err}",
            )

    def get_page_state(self, max_text_bytes: int = 32768, max_elements: int = 100) -> PageState:
        if not self.is_running():
            raise ToolExecutionError("Browser is not running. Navigate to a URL first.")

        url = self._page.url
        title = self._page.title()

        # Extract visible text from body
        try:
            raw_text = self._page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
            cleaned_text = re.sub(r"\n{3,}", "\n\n", raw_text.strip())
        except Exception as err:
            logger.warning("Error evaluating innerText: %s", err)
            cleaned_text = ""

        truncated = False
        text_bytes = cleaned_text.encode("utf-8")
        if len(text_bytes) > max_text_bytes:
            cleaned_text = text_bytes[:max_text_bytes].decode("utf-8", errors="ignore") + "\n... [Content truncated due to length limits]"
            truncated = True

        # Extract interactive elements
        elements: list[BrowserElement] = []
        try:
            # Query candidate interactive elements
            js_query = """
            () => {
                const candidates = Array.from(document.querySelectorAll('a[href], button, input, textarea, select'));
                return candidates.filter(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                }).slice(0, 150).map((el, index) => {
                    return {
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.title || el.ariaLabel || '').trim().slice(0, 80),
                        type: el.type || null,
                        name: el.name || el.id || null,
                        placeholder: el.placeholder || null,
                        index: index
                    };
                });
            }
            """
            raw_elements = self._page.evaluate(js_query)

            for idx, item in enumerate(raw_elements[:max_elements], start=1):
                tag = item.get("tag", "element")
                el_type = item.get("type")
                is_pwd = (el_type or "").lower() == "password"
                name = item.get("name")
                selector_index = item.get("index", idx - 1)

                # Selector strategy using stable nth-match on interactive tags
                selector = f"a[href], button, input, textarea, select >> nth={selector_index}"

                elements.append(
                    BrowserElement(
                        element_id=idx,
                        tag=tag,
                        text=item.get("text", ""),
                        element_type=el_type,
                        name=name,
                        placeholder=item.get("placeholder"),
                        selector=selector,
                        is_interactive=True,
                        is_sensitive=is_pwd,
                    )
                )
        except Exception as err:
            logger.warning("Error discovering page interactive elements: %s", err)

        return PageState(
            url=url,
            title=title,
            text_content=cleaned_text,
            elements=elements,
            truncated=truncated,
        )

    def click(self, element: BrowserElement, timeout_seconds: float = 15.0) -> BrowserActionResult:
        if not self.is_running():
            raise ToolExecutionError("Browser is not running.")

        timeout_ms = int(timeout_seconds * 1000)
        try:
            locator = self._page.locator(element.selector)
            if locator.count() == 0:
                return BrowserActionResult(
                    success=False,
                    action="click",
                    target_element_id=element.element_id,
                    current_url=self._page.url,
                    current_title=self._page.title(),
                    message=f"Element [#{element.element_id}] was not found or is stale.",
                    error="Element not found on current page",
                )

            locator.first.click(timeout=timeout_ms)
            # Short wait for any potential navigation or DOM update
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=2000)
            except Exception:
                pass

            curr_url = self._page.url
            curr_title = self._page.title()
            label = element.text or element.name or element.tag
            msg = f"Successfully clicked element [#{element.element_id}] ('{label}'). Current page: '{curr_title}' ({curr_url})"
            logger.info(msg)
            return BrowserActionResult(
                success=True,
                action="click",
                target_element_id=element.element_id,
                current_url=curr_url,
                current_title=curr_title,
                message=msg,
            )
        except Exception as err:
            logger.error("Click on element [#{element.element_id}] failed: %s", err)
            return BrowserActionResult(
                success=False,
                action="click",
                target_element_id=element.element_id,
                current_url=self._page.url if self._page else "",
                current_title=self._page.title() if self._page else "",
                message=f"Click failed: {err}",
                error=str(err),
            )

    def type(self, element: BrowserElement, text: str, timeout_seconds: float = 15.0) -> BrowserActionResult:
        if not self.is_running():
            raise ToolExecutionError("Browser is not running.")

        timeout_ms = int(timeout_seconds * 1000)
        try:
            locator = self._page.locator(element.selector)
            if locator.count() == 0:
                return BrowserActionResult(
                    success=False,
                    action="type",
                    target_element_id=element.element_id,
                    current_url=self._page.url,
                    current_title=self._page.title(),
                    message=f"Element [#{element.element_id}] was not found or is stale.",
                    error="Element not found on current page",
                )

            locator.first.fill(text, timeout=timeout_ms)
            curr_url = self._page.url
            curr_title = self._page.title()

            display_text = "******" if element.is_sensitive else f"'{text}'"
            msg = f"Entered {display_text} into element [#{element.element_id}]."
            logger.info("Typed value into element [#{element.element_id}] (sensitive=%s)", element.is_sensitive)
            return BrowserActionResult(
                success=True,
                action="type",
                target_element_id=element.element_id,
                current_url=curr_url,
                current_title=curr_title,
                message=msg,
            )
        except Exception as err:
            logger.error("Typing into element [#{element.element_id}] failed: %s", err)
            return BrowserActionResult(
                success=False,
                action="type",
                target_element_id=element.element_id,
                current_url=self._page.url if self._page else "",
                current_title=self._page.title() if self._page else "",
                message=f"Typing failed: {err}",
                error=str(err),
            )

    def scroll(self, direction: str = "down", amount: int = 500) -> BrowserActionResult:
        if not self.is_running():
            raise ToolExecutionError("Browser is not running.")

        delta = amount if direction.lower() == "down" else -amount
        try:
            self._page.evaluate(f"window.scrollBy(0, {delta})")
            return BrowserActionResult(
                success=True,
                action="scroll",
                current_url=self._page.url,
                current_title=self._page.title(),
                message=f"Scrolled {direction} by {amount} pixels.",
            )
        except Exception as err:
            return BrowserActionResult(
                success=False,
                action="scroll",
                current_url=self._page.url,
                current_title=self._page.title(),
                message=f"Scroll failed: {err}",
                error=str(err),
            )

    def go_back(self) -> BrowserActionResult:
        if not self.is_running():
            raise ToolExecutionError("Browser is not running.")

        try:
            resp = self._page.go_back()
            msg = f"Navigated back to '{self._page.title()}' ({self._page.url})"
            return BrowserActionResult(
                success=True,
                action="back",
                current_url=self._page.url,
                current_title=self._page.title(),
                message=msg,
            )
        except Exception as err:
            return BrowserActionResult(
                success=False,
                action="back",
                current_url=self._page.url,
                current_title=self._page.title(),
                message=f"Navigate back failed: {err}",
                error=str(err),
            )

    def go_forward(self) -> BrowserActionResult:
        if not self.is_running():
            raise ToolExecutionError("Browser is not running.")

        try:
            resp = self._page.go_forward()
            msg = f"Navigated forward to '{self._page.title()}' ({self._page.url})"
            return BrowserActionResult(
                success=True,
                action="forward",
                current_url=self._page.url,
                current_title=self._page.title(),
                message=msg,
            )
        except Exception as err:
            return BrowserActionResult(
                success=False,
                action="forward",
                current_url=self._page.url,
                current_title=self._page.title(),
                message=f"Navigate forward failed: {err}",
                error=str(err),
            )


class MockBrowserProvider(BrowserProvider):
    """Deterministic in-memory browser provider for testing."""

    def __init__(self) -> None:
        self._running = False
        self._current_url = "about:blank"
        self._current_title = ""
        self._text_content = ""
        self._elements: list[BrowserElement] = []
        self._history: list[str] = []
        self._history_index: int = -1
        self.actions_log: list[str] = []

    def set_mock_page(self, url: str, title: str, text: str, elements: Optional[list[BrowserElement]] = None) -> None:
        """Configure mock page contents directly."""
        self._current_url = url
        self._current_title = title
        self._text_content = text
        self._elements = elements or []

    def start(self, headless: bool = True) -> None:
        self._running = True
        self.actions_log.append(f"start(headless={headless})")

    def stop(self) -> None:
        self._running = False
        self.actions_log.append("stop")

    def is_running(self) -> bool:
        return self._running

    def navigate(self, url: str, timeout_seconds: float = 30.0) -> NavigationResult:
        if not self._running:
            self.start()
        self._current_url = url
        if not self._current_title:
            self._current_title = f"Page for {url}"
        self._history.append(url)
        self._history_index = len(self._history) - 1
        self.actions_log.append(f"navigate({url})")
        return NavigationResult(success=True, url=self._current_url, title=self._current_title, status_code=200)

    def get_page_state(self, max_text_bytes: int = 32768, max_elements: int = 100) -> PageState:
        if not self._running:
            raise ToolExecutionError("Mock browser is not running.")
        text = self._text_content or f"Mock text content for {self._current_url}"
        elements = self._elements or [
            BrowserElement(element_id=1, tag="a", text="Home", selector="a >> nth=0"),
            BrowserElement(element_id=2, tag="input", element_type="text", name="q", placeholder="Search", selector="input >> nth=0"),
            BrowserElement(element_id=3, tag="button", text="Submit", selector="button >> nth=0"),
        ]
        return PageState(
            url=self._current_url,
            title=self._current_title or "Mock Page Title",
            text_content=text[:max_text_bytes],
            elements=elements[:max_elements],
        )

    def click(self, element: BrowserElement, timeout_seconds: float = 15.0) -> BrowserActionResult:
        self.actions_log.append(f"click({element.element_id})")
        return BrowserActionResult(
            success=True,
            action="click",
            target_element_id=element.element_id,
            current_url=self._current_url,
            current_title=self._current_title,
            message=f"Clicked element [#{element.element_id}]",
        )

    def type(self, element: BrowserElement, text: str, timeout_seconds: float = 15.0) -> BrowserActionResult:
        self.actions_log.append(f"type({element.element_id})")
        return BrowserActionResult(
            success=True,
            action="type",
            target_element_id=element.element_id,
            current_url=self._current_url,
            current_title=self._current_title,
            message=f"Typed '{text}' into element [#{element.element_id}]",
        )


    def scroll(self, direction: str = "down", amount: int = 500) -> BrowserActionResult:
        self.actions_log.append(f"scroll({direction}, {amount})")
        return BrowserActionResult(
            success=True,
            action="scroll",
            current_url=self._current_url,
            current_title=self._current_title,
            message=f"Scrolled {direction}",
        )

    def go_back(self) -> BrowserActionResult:
        self.actions_log.append("back")
        if self._history_index > 0:
            self._history_index -= 1
            self._current_url = self._history[self._history_index]
        return BrowserActionResult(
            success=True,
            action="back",
            current_url=self._current_url,
            current_title=self._current_title,
            message="Navigated back",
        )

    def go_forward(self) -> BrowserActionResult:
        self.actions_log.append("forward")
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._current_url = self._history[self._history_index]
        return BrowserActionResult(
            success=True,
            action="forward",
            current_url=self._current_url,
            current_title=self._current_title,
            message="Navigated forward",
        )
