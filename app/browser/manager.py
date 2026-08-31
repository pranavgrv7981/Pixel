"""High-level BrowserManager coordinating sessions, URL validation, and untrusted content boundaries."""

from datetime import datetime, timezone
import time
from typing import Optional
from urllib.parse import quote_plus
import uuid

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolExecutionError, ToolValidationError
from app.core.logging import get_logger
from app.browser.models import (
    BrowserActionResult,
    BrowserElement,
    BrowserSessionInfo,
    NavigationResult,
    PageState,
)
from app.browser.provider import BrowserProvider, PlaywrightBrowserProvider
from app.browser.security import URLValidator, WebSecuritySanitizer


class BrowserManager:
    """Orchestrates browser session lifecycles, navigation, element interactions, and prompt injection defense."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        provider: Optional[BrowserProvider] = None,
        validator: Optional[URLValidator] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or PlaywrightBrowserProvider()
        self.validator = validator or URLValidator(allow_local_network=self.settings.allow_local_network)
        self.sanitizer = WebSecuritySanitizer()
        self.logger = get_logger("browser.manager")

        self._session_info: Optional[BrowserSessionInfo] = None
        self._current_page_state: Optional[PageState] = None

    def _ensure_session(self) -> BrowserSessionInfo:
        """Verify active session or spin up a new session, enforcing idle timeouts."""
        now = datetime.now(timezone.utc)

        # Check idle session timeout
        if self._session_info is not None and self._session_info.is_active:
            idle_seconds = (now - self._session_info.last_active_at).total_seconds()
            if idle_seconds > self.settings.browser_session_timeout_seconds:
                self.logger.warning(
                    "Browser session '%s' expired after %.1f idle seconds; recycling session",
                    self._session_info.session_id,
                    idle_seconds,
                )
                self.close_session()

        if self._session_info is None or not self._session_info.is_active or not self.provider.is_running():
            session_id = str(uuid.uuid4())
            self.logger.info("Initializing new browser session '%s' (headless=%s)", session_id, self.settings.browser_headless)
            self.provider.start(headless=self.settings.browser_headless)
            self._session_info = BrowserSessionInfo(
                session_id=session_id,
                is_active=True,
                headless=self.settings.browser_headless,
                created_at=now,
                last_active_at=now,
            )
            self._current_page_state = None

        self._session_info.last_active_at = now
        return self._session_info

    def open_url(self, url: str) -> tuple[NavigationResult, PageState, str]:
        """Validate URL, navigate, capture page snapshot, and return untrusted wrapped context."""
        validated_url = self.validator.validate_url(url)
        session = self._ensure_session()

        nav_res = self.provider.navigate(validated_url, timeout_seconds=self.settings.browser_page_timeout_seconds)
        if not nav_res.success:
            raise ToolExecutionError(f"Failed to open '{validated_url}': {nav_res.error}")

        session.navigation_count += 1
        session.current_url = nav_res.url
        session.current_title = nav_res.title
        session.last_active_at = datetime.now(timezone.utc)

        # Extract page state
        page_state = self.provider.get_page_state(
            max_text_bytes=self.settings.max_browser_text_bytes,
            max_elements=self.settings.max_browser_elements,
        )
        self._current_page_state = page_state

        elements_summary = page_state.format_elements_summary()
        wrapped_context = self.sanitizer.wrap_untrusted_content(
            url=page_state.url,
            title=page_state.title,
            content=page_state.text_content,
            elements_summary=elements_summary,
        )

        return nav_res, page_state, wrapped_context

    def search(self, query: str) -> tuple[NavigationResult, PageState, str]:
        """Perform a web search using a safe privacy-oriented search engine."""
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ToolValidationError("Search query cannot be empty")

        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(cleaned_query)}"
        self.logger.info("Performing browser search for '%s'", cleaned_query)
        return self.open_url(search_url)

    def get_current_page(self) -> tuple[PageState, str]:
        """Inspect and return current page text content and elements snapshot."""
        self._ensure_session()
        if not self.provider.is_running():
            raise ToolExecutionError("No active webpage is currently loaded. Use 'browser_open' first.")

        page_state = self.provider.get_page_state(
            max_text_bytes=self.settings.max_browser_text_bytes,
            max_elements=self.settings.max_browser_elements,
        )
        self._current_page_state = page_state

        elements_summary = page_state.format_elements_summary()
        wrapped_context = self.sanitizer.wrap_untrusted_content(
            url=page_state.url,
            title=page_state.title,
            content=page_state.text_content,
            elements_summary=elements_summary,
        )
        return page_state, wrapped_context

    def click_element(self, element_id: int) -> BrowserActionResult:
        """Click an identified interactive element on the current page."""
        self._ensure_session()
        if self._current_page_state is None:
            raise ToolExecutionError("No active page snapshot. Open a URL before clicking elements.")

        element = self._current_page_state.get_element(element_id)
        if element is None:
            max_id = len(self._current_page_state.elements)
            raise ToolValidationError(
                f"Element ID [#{element_id}] is invalid or stale. "
                f"Available element IDs on current page: 1 to {max_id}. Call 'browser_get_page' to view fresh elements."
            )

        result = self.provider.click(element, timeout_seconds=self.settings.browser_action_timeout_seconds)
        if result.success:
            # Refresh page state after click
            try:
                self._current_page_state = self.provider.get_page_state(
                    max_text_bytes=self.settings.max_browser_text_bytes,
                    max_elements=self.settings.max_browser_elements,
                )
                if self._session_info:
                    self._session_info.current_url = self._current_page_state.url
                    self._session_info.current_title = self._current_page_state.title
            except Exception:
                pass

        return result

    def type_element(self, element_id: int, text: str) -> BrowserActionResult:
        """Enter text into an identified input element on the current page."""
        self._ensure_session()
        if self._current_page_state is None:
            raise ToolExecutionError("No active page snapshot. Open a URL before typing into elements.")

        element = self._current_page_state.get_element(element_id)
        if element is None:
            max_id = len(self._current_page_state.elements)
            raise ToolValidationError(
                f"Element ID [#{element_id}] is invalid or stale. "
                f"Available element IDs on current page: 1 to {max_id}. Call 'browser_get_page' to view fresh elements."
            )

        result = self.provider.type(element, text, timeout_seconds=self.settings.browser_action_timeout_seconds)
        if result.success:
            try:
                self._current_page_state = self.provider.get_page_state(
                    max_text_bytes=self.settings.max_browser_text_bytes,
                    max_elements=self.settings.max_browser_elements,
                )
            except Exception:
                pass

        return result

    def scroll(self, direction: str = "down", amount: int = 500) -> BrowserActionResult:
        """Scroll the current webpage view."""
        self._ensure_session()
        dir_clean = direction.lower().strip()
        if dir_clean not in ("up", "down"):
            raise ToolValidationError(f"Invalid scroll direction '{direction}'. Must be 'up' or 'down'.")

        result = self.provider.scroll(direction=dir_clean, amount=amount)
        # Update page snapshot after scroll
        if result.success:
            try:
                self._current_page_state = self.provider.get_page_state(
                    max_text_bytes=self.settings.max_browser_text_bytes,
                    max_elements=self.settings.max_browser_elements,
                )
            except Exception:
                pass
        return result

    def back(self) -> BrowserActionResult:
        """Navigate backward in browsing history."""
        self._ensure_session()
        result = self.provider.go_back()
        if result.success:
            try:
                self._current_page_state = self.provider.get_page_state(
                    max_text_bytes=self.settings.max_browser_text_bytes,
                    max_elements=self.settings.max_browser_elements,
                )
            except Exception:
                pass
        return result

    def forward(self) -> BrowserActionResult:
        """Navigate forward in browsing history."""
        self._ensure_session()
        result = self.provider.go_forward()
        if result.success:
            try:
                self._current_page_state = self.provider.get_page_state(
                    max_text_bytes=self.settings.max_browser_text_bytes,
                    max_elements=self.settings.max_browser_elements,
                )
            except Exception:
                pass
        return result

    def close_session(self) -> bool:
        """Safely terminate the browser process and reset session state."""
        try:
            self.provider.stop()
            if self._session_info:
                self._session_info.is_active = False
            self._current_page_state = None
            self.logger.info("Browser session closed cleanly.")
            return True
        except Exception as err:
            self.logger.error("Error closing browser session: %s", err)
            return False

    def get_session_info(self) -> Optional[BrowserSessionInfo]:
        """Return active session info if initialized."""
        return self._session_info
