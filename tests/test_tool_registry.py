"""Tests for app/tools/registry.py."""

import pytest

from app.core.exceptions import ToolAlreadyExistsError, ToolNotFoundError, ToolValidationError
from app.tools.demo import GetCurrentTimeTool, SafeCalculateTool
from app.tools.registry import ToolRegistry


def test_registry_register_and_lookup() -> None:
    """Verify tool registration and lookup."""
    registry = ToolRegistry()
    tool = GetCurrentTimeTool()

    assert not registry.has("get_current_time")
    registry.register(tool)
    assert registry.has("get_current_time")
    assert registry.get("get_current_time") is tool
    assert len(registry.list()) == 1


def test_registry_register_duplicate_raises() -> None:
    """Verify duplicate tool registration raises ToolAlreadyExistsError."""
    registry = ToolRegistry()
    tool = GetCurrentTimeTool()
    registry.register(tool)

    with pytest.raises(ToolAlreadyExistsError):
        registry.register(tool)


def test_registry_register_invalid_type_raises() -> None:
    """Verify registering a non-Tool raises ToolValidationError."""
    registry = ToolRegistry()
    with pytest.raises(ToolValidationError):
        registry.register("not_a_tool")  # type: ignore


def test_registry_get_missing_raises() -> None:
    """Verify looking up a missing tool raises ToolNotFoundError."""
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("non_existent_tool")


def test_registry_unregister_success() -> None:
    """Verify unregistering a tool removes it from the registry."""
    registry = ToolRegistry()
    tool = GetCurrentTimeTool()
    registry.register(tool)

    removed = registry.unregister("get_current_time")
    assert removed is tool
    assert not registry.has("get_current_time")
    assert len(registry.list()) == 0


def test_registry_unregister_missing_raises() -> None:
    """Verify unregistering a non-existent tool raises ToolNotFoundError."""
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.unregister("missing")


def test_registry_clear() -> None:
    """Verify clear removes all registered tools."""
    registry = ToolRegistry()
    registry.register(GetCurrentTimeTool())
    registry.register(SafeCalculateTool())
    assert len(registry.list()) == 2

    registry.clear()
    assert len(registry.list()) == 0


def test_registry_get_schemas() -> None:
    """Verify get_schemas produces Ollama-compatible function definitions."""
    registry = ToolRegistry()
    registry.register(GetCurrentTimeTool())
    registry.register(SafeCalculateTool())

    schemas = registry.get_schemas()
    assert len(schemas) == 2
    names = [s["function"]["name"] for s in schemas]
    assert "get_current_time" in names
    assert "calculate" in names
