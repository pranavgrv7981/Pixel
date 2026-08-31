"""Data models and schemas for browser automation."""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class BrowserElement(BaseModel):
    """Structured representation of an interactive or informational page element."""

    element_id: int = Field(description="Deterministic 1-indexed identifier for the element on the current page")
    tag: str = Field(description="HTML tag name (e.g. 'a', 'button', 'input', 'textarea')")
    text: str = Field(default="", description="Visible text or label of the element")
    element_type: Optional[str] = Field(default=None, description="Input type if applicable (e.g. 'text', 'submit', 'checkbox')")
    name: Optional[str] = Field(default=None, description="HTML name or id attribute")
    placeholder: Optional[str] = Field(default=None, description="Input placeholder text")
    selector: str = Field(description="Internal CSS/XPath selector mapped to this element")
    is_interactive: bool = Field(default=True, description="Whether the element supports click or typing")
    is_sensitive: bool = Field(default=False, description="Whether the element handles sensitive data (e.g. passwords)")


class PageState(BaseModel):
    """Snapshot of a browser page including bounded content and mapped elements."""

    url: str = Field(description="Current page URL")
    title: str = Field(default="", description="Current page title")
    text_content: str = Field(default="", description="Cleaned, bounded visible text content of the page")
    elements: list[BrowserElement] = Field(default_factory=list, description="List of interactive elements on the page")
    truncated: bool = Field(default=False, description="Whether the text content was truncated to fit byte limits")
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_element(self, element_id: int) -> Optional[BrowserElement]:
        """Find element by its 1-indexed element_id."""
        for el in self.elements:
            if el.element_id == element_id:
                return el
        return None

    def format_elements_summary(self, max_items: int = 30) -> str:
        """Format interactive elements into a clean, model-friendly reference list."""
        if not self.elements:
            return "No interactive elements identified."

        lines = []
        for el in self.elements[:max_items]:
            kind = el.element_type or el.tag
            label = el.text[:60] if el.text else (el.placeholder or el.name or "")
            label_display = f' "{label}"' if label else ""
            lines.append(f"[#{el.element_id}] [{kind}]{label_display}")

        if len(self.elements) > max_items:
            lines.append(f"... ({len(self.elements) - max_items} more elements omitted)")

        return "\n".join(lines)


class NavigationResult(BaseModel):
    """Result of a browser navigation operation."""

    success: bool
    url: str
    title: str = ""
    status_code: Optional[int] = None
    error: Optional[str] = None


class BrowserActionResult(BaseModel):
    """Result of an interaction with a browser element or page state."""

    success: bool
    action: str
    target_element_id: Optional[int] = None
    current_url: str = ""
    current_title: str = ""
    message: str = ""
    error: Optional[str] = None


class BrowserSessionInfo(BaseModel):
    """Metadata regarding an active or terminated browser session."""

    session_id: str
    is_active: bool
    headless: bool
    current_url: Optional[str] = None
    current_title: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    navigation_count: int = 0
