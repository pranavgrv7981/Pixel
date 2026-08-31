"""Tool registry for registering, discovering, and inspecting available tools."""

from typing import Optional

from app.core.exceptions import ToolAlreadyExistsError, ToolNotFoundError, ToolValidationError
from app.core.logging import get_logger
from app.tools.base import Tool

logger = get_logger("tools")


class ToolRegistry:
    """Central registry of executable tools accessible to the assistant."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a new tool in the registry.

        Raises:
            ToolValidationError: If tool is not an instance of Tool.
            ToolAlreadyExistsError: If a tool with the same name is already registered.
        """
        if not isinstance(tool, Tool):
            raise ToolValidationError(f"Expected Tool instance, got {type(tool).__name__}")

        if tool.name in self._tools:
            logger.warning("Attempted to register duplicate tool '%s'", tool.name)
            raise ToolAlreadyExistsError(f"Tool with name '{tool.name}' is already registered")

        self._tools[tool.name] = tool
        logger.info("Registered tool '%s' (risk=%s)", tool.name, tool.risk_level.value)

    def unregister(self, name: str) -> Tool:
        """Remove a tool from the registry.

        Raises:
            ToolNotFoundError: If the tool is not found.
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Cannot unregister: tool '{name}' not found")

        removed = self._tools.pop(name)
        logger.info("Unregistered tool '%s'", name)
        return removed

    def get(self, name: str) -> Tool:
        """Retrieve a registered tool by name.

        Raises:
            ToolNotFoundError: If the tool is not found.
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def has(self, name: str) -> bool:
        """Check if a tool exists in the registry."""
        return name in self._tools

    def list(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        logger.info("ToolRegistry cleared")

    def get_schemas(self) -> list[dict[str, object]]:
        """Return list of JSON schemas for all registered tools in Ollama format."""
        return [tool.get_schema() for tool in self._tools.values()]
