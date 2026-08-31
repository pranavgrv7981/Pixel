"""Base abstractions for tools, execution results, and risk classification."""

from abc import ABC, abstractmethod
from enum import Enum
import json
import re
from typing import Any, Mapping, Optional, Type

from pydantic import BaseModel, Field, ValidationError

from app.core.exceptions import ToolExecutionError, ToolValidationError

TOOL_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class RiskLevel(str, Enum):
    """Classification of tool operation risk for safety and permission controls."""

    READ = "READ"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToolResult(BaseModel):
    """Structured result returned by tool execution."""

    success: bool = Field(description="Indicates whether tool execution succeeded")
    data: Any = Field(default=None, description="Output payload produced by the tool")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    message: Optional[str] = Field(default=None, description="Human-readable informational message")

    def to_llm_content(self) -> str:
        """Serialize result to a format suitable for feeding back to an LLM."""
        if not self.success:
            payload = {"status": "error", "error": self.error or "Unknown tool error"}
            if self.message:
                payload["message"] = self.message
            return json.dumps(payload, default=str)

        if isinstance(self.data, (dict, list)):
            return json.dumps(self.data, default=str)
        elif self.data is not None:
            return str(self.data)
        elif self.message:
            return self.message
        return json.dumps({"status": "success"})


class Tool(ABC):
    """Abstract base class defining a first-class executable tool."""

    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel = RiskLevel.LOW,
        args_model: Optional[Type[BaseModel]] = None,
    ) -> None:
        self.name: str = self._validate_name(name)
        self.description: str = self._validate_description(description)
        self.risk_level: RiskLevel = risk_level
        self.args_model: Optional[Type[BaseModel]] = args_model

    @staticmethod
    def _validate_name(name: str) -> str:
        """Validate that tool name satisfies deterministic naming rules."""
        if not isinstance(name, str):
            raise ToolValidationError(f"Tool name must be a string, got {type(name).__name__}")
        cleaned = name.strip()
        if not cleaned:
            raise ToolValidationError("Tool name cannot be empty or whitespace-only")
        if not TOOL_NAME_REGEX.match(cleaned):
            raise ToolValidationError(
                f"Invalid tool name '{name}'. Must be 1-64 alphanumeric characters, underscores, or hyphens."
            )
        return cleaned

    @staticmethod
    def _validate_description(desc: str) -> str:
        """Validate tool description."""
        if not isinstance(desc, str) or not desc.strip():
            raise ToolValidationError("Tool description must be a non-empty string")
        return desc.strip()

    def get_schema(self) -> dict[str, Any]:
        """Return the function tool schema formatted for Ollama tool calling."""
        parameters: dict[str, Any] = {"type": "object", "properties": {}}
        if self.args_model:
            parameters = self.args_model.model_json_schema()
            # Clean schema metadata not needed by LLM
            parameters.pop("title", None)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    def validate_args(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """Validate input arguments against args_model schema if present."""
        if not isinstance(args, Mapping):
            raise ToolValidationError(f"Tool arguments must be a dictionary/mapping, got {type(args).__name__}")

        if self.args_model is not None:
            try:
                validated = self.args_model.model_validate(args)
                return validated.model_dump()
            except ValidationError as err:
                raise ToolValidationError(f"Invalid arguments for tool '{self.name}': {err}") from err
        return dict(args)

    def _check_permission(self, args: dict[str, Any]) -> None:
        """Interception point for Phase 4 permission checks."""
        # By design in Phase 3, permission checks are a pass-through hook
        pass

    def execute(self, args: Mapping[str, Any]) -> ToolResult:
        """Execute the tool with parameter validation, permission checks, and error handling."""
        try:
            validated_args = self.validate_args(args)
            self._check_permission(validated_args)
            result = self._run(validated_args)

            if isinstance(result, ToolResult):
                return result
            return ToolResult(success=True, data=result)

        except ToolValidationError as err:
            return ToolResult(success=False, error=str(err))
        except Exception as err:
            return ToolResult(
                success=False,
                error=f"Runtime error in tool '{self.name}': {err}",
            )

    @abstractmethod
    def _run(self, args: dict[str, Any]) -> Any:
        """Internal execution method implemented by concrete tools."""
        pass
