"""Persistent memory tools integrated with ToolRegistry and PermissionManager."""

from typing import Any, Optional
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.memory.manager import MemoryManager
from app.memory.models import MemoryCategory
from app.tools.base import RiskLevel, Tool, ToolResult


# --- Parameter Schemas ---

class RememberMemoryArgs(BaseModel):
    """Input arguments for storing or updating a persistent memory."""

    category: str = Field(
        description=f"Memory category: {', '.join(c.value for c in MemoryCategory)}",
    )
    key: str = Field(
        description="Key/name of the fact or preference to remember (e.g. 'main_project', 'favorite_editor')",
    )
    value: str = Field(
        description="The information, preference, or fact to store",
    )
    importance: Optional[int] = Field(
        default=5,
        ge=1,
        le=10,
        description="Importance score from 1 (low) to 10 (critical), default 5",
    )


class RecallMemoryArgs(BaseModel):
    """Input arguments for searching or retrieving stored memories."""

    query: Optional[str] = Field(
        default=None,
        description="Optional search term or keyword to match against memory keys or values",
    )
    category: Optional[str] = Field(
        default=None,
        description=f"Optional category filter: {', '.join(c.value for c in MemoryCategory)}",
    )


class ForgetMemoryArgs(BaseModel):
    """Input arguments for explicitly deleting a stored memory."""

    key: str = Field(
        description="The key of the memory to forget",
    )
    category: Optional[str] = Field(
        default=None,
        description=f"Optional category filter: {', '.join(c.value for c in MemoryCategory)}",
    )


# --- Base Memory Tool ---

class MemoryTool(Tool):
    """Base class for tools interacting with the persistent MemoryManager."""

    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        args_model: Optional[type[BaseModel]] = None,
        memory_manager: Optional[MemoryManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(name=name, description=description, risk_level=risk_level, args_model=args_model)
        self.settings = settings or get_settings()
        self.memory_manager = memory_manager or MemoryManager(settings=self.settings)


# --- Tool Implementations ---

class RememberMemoryTool(MemoryTool):
    """Tool to explicitly store or update a persistent user fact or preference."""

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="remember_memory",
            description="Persist an explicit user preference, project fact, workflow rule, or context for future sessions.",
            risk_level=RiskLevel.LOW,
            args_model=RememberMemoryArgs,
            memory_manager=memory_manager,
            settings=settings,
        )

    def validate_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        validated = super().validate_args(arguments)
        # Verify valid category
        self.memory_manager.parse_category(validated["category"])
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        rec = self.memory_manager.remember(
            category=args["category"],
            key=args["key"],
            value=args["value"],
            importance=args.get("importance") or 5,
        )
        return ToolResult(
            success=True,
            data={
                "id": rec.id,
                "category": rec.category.value,
                "key": rec.key,
                "value": rec.value,
                "importance": rec.importance,
                "message": f"Successfully remembered [{rec.category.value}] {rec.key} = '{rec.value}'.",
            },
        )


class RecallMemoryTool(MemoryTool):
    """Tool to search and inspect stored persistent memories."""

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="recall_memory",
            description="Retrieve stored user facts, preferences, or project details by keyword or category.",
            risk_level=RiskLevel.READ,
            args_model=RecallMemoryArgs,
            memory_manager=memory_manager,
            settings=settings,
        )

    def validate_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        validated = super().validate_args(arguments)
        if validated.get("category"):
            self.memory_manager.parse_category(validated["category"])
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        records = self.memory_manager.recall(
            query=args.get("query"),
            category=args.get("category"),
        )
        data = [
            {
                "category": r.category.value,
                "key": r.key,
                "value": r.value,
                "importance": r.importance,
            }
            for r in records
        ]
        return ToolResult(
            success=True,
            data={
                "count": len(data),
                "memories": data,
            },
        )


class ForgetMemoryTool(MemoryTool):
    """Tool to delete a stored memory (requires user confirmation)."""

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="forget_memory",
            description="Explicitly remove/delete a stored memory item by key.",
            risk_level=RiskLevel.MEDIUM,
            args_model=ForgetMemoryArgs,
            memory_manager=memory_manager,
            settings=settings,
        )

    def validate_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        validated = super().validate_args(arguments)
        if validated.get("category"):
            self.memory_manager.parse_category(validated["category"])
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        key = args["key"]
        cat = args.get("category")
        deleted = self.memory_manager.forget(key=key, category=cat)
        if deleted:
            msg = f"Memory with key '{key}' was successfully forgotten."
        else:
            msg = f"No memory found with key '{key}' to forget."

        return ToolResult(
            success=deleted,
            data={
                "key": key,
                "deleted": deleted,
                "message": msg,
            },
            error=None if deleted else f"Memory key '{key}' not found",
        )

