"""Tests for app/tools/base.py and app/tools/demo.py."""

from typing import Any, Optional
from pydantic import BaseModel, Field
import pytest

from app.core.exceptions import ToolValidationError
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.demo import GetCurrentTimeTool, SafeCalculateTool


class SampleArgs(BaseModel):
    query: str = Field(description="Search query string")
    count: Optional[int] = Field(default=5, description="Number of results")


class SampleTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="sample_tool",
            description="A sample tool for testing.",
            risk_level=RiskLevel.LOW,
            args_model=SampleArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"query": args["query"], "count": args["count"]})


def test_risk_level_values() -> None:
    """Verify standard risk level enumeration."""
    assert RiskLevel.READ.value == "READ"
    assert RiskLevel.LOW.value == "LOW"
    assert RiskLevel.MEDIUM.value == "MEDIUM"
    assert RiskLevel.HIGH.value == "HIGH"
    assert RiskLevel.CRITICAL.value == "CRITICAL"


def test_tool_result_serialization() -> None:
    """Verify ToolResult to_llm_content formats properly."""
    res_success = ToolResult(success=True, data={"time": "12:00:00"})
    assert '"time": "12:00:00"' in res_success.to_llm_content()

    res_error = ToolResult(success=False, error="Invalid parameter", message="Failed")
    llm_str = res_error.to_llm_content()
    assert '"status": "error"' in llm_str
    assert '"error": "Invalid parameter"' in llm_str
    assert '"message": "Failed"' in llm_str


@pytest.mark.parametrize(
    "valid_name",
    ["valid_name", "tool-1", "TOOL_NAME", "get_current_time", "calculate123", "a" * 64],
)
def test_tool_name_validation_valid(valid_name: str) -> None:
    """Verify valid tool names pass validation."""
    tool = SampleTool()
    tool.name = Tool._validate_name(valid_name)
    assert tool.name == valid_name


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "   ",
        "tool with spaces",
        "tool@name!",
        "tool#1",
        "a" * 65,  # Exceeds 64 characters
    ],
)
def test_tool_name_validation_invalid(invalid_name: str) -> None:
    """Verify invalid tool names raise ToolValidationError."""
    with pytest.raises(ToolValidationError):
        Tool._validate_name(invalid_name)


def test_tool_non_string_name() -> None:
    """Verify non-string tool name raises ToolValidationError."""
    with pytest.raises(ToolValidationError):
        Tool._validate_name(12345)  # type: ignore


def test_tool_description_validation() -> None:
    """Verify description validation."""
    assert Tool._validate_description("Valid description") == "Valid description"

    with pytest.raises(ToolValidationError):
        Tool._validate_description("")

    with pytest.raises(ToolValidationError):
        Tool._validate_description("   ")


def test_tool_schema_generation() -> None:
    """Verify get_schema produces standard Ollama function schema."""
    tool = SampleTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "sample_tool"
    assert schema["function"]["description"] == "A sample tool for testing."
    params = schema["function"]["parameters"]
    assert params["type"] == "object"
    assert "query" in params["properties"]


def test_tool_argument_validation_success() -> None:
    """Verify argument validation accepts valid parameters."""
    tool = SampleTool()
    validated = tool.validate_args({"query": "python test", "count": 10})
    assert validated == {"query": "python test", "count": 10}


def test_tool_argument_validation_missing_required() -> None:
    """Verify missing required parameter raises ToolValidationError."""
    tool = SampleTool()
    with pytest.raises(ToolValidationError):
        tool.validate_args({"count": 5})


def test_tool_argument_validation_type_error() -> None:
    """Verify wrong parameter type raises ToolValidationError."""
    tool = SampleTool()
    with pytest.raises(ToolValidationError):
        tool.validate_args({"query": 12345, "count": "not_an_int"})


def test_tool_argument_validation_non_dict() -> None:
    """Verify non-mapping arguments raise ToolValidationError."""
    tool = SampleTool()
    with pytest.raises(ToolValidationError):
        tool.validate_args("query string")  # type: ignore


def test_get_current_time_tool() -> None:
    """Verify GetCurrentTimeTool executes and returns current time."""
    tool = GetCurrentTimeTool()
    assert tool.name == "get_current_time"
    assert tool.risk_level == RiskLevel.READ

    result = tool.execute({})
    assert result.success is True
    assert "current_time" in result.data
    assert "The current time is" in result.message


def test_get_current_time_custom_format() -> None:
    """Verify GetCurrentTimeTool supports custom strftime format."""
    tool = GetCurrentTimeTool()
    result = tool.execute({"format": "%Y"})
    assert result.success is True
    assert len(result.data["current_time"]) == 4


def test_safe_calculate_tool_arithmetic() -> None:
    """Verify SafeCalculateTool evaluates valid math expressions."""
    calc = SafeCalculateTool()
    assert calc.name == "calculate"
    assert calc.risk_level == RiskLevel.READ

    # Addition and multiplication precedence
    res1 = calc.execute({"expression": "2 + 3 * 4"})
    assert res1.success is True
    assert res1.data["result"] == 14

    # Parentheses and powers
    res2 = calc.execute({"expression": "(10 - 2) / 4 + 2 ** 3"})
    assert res2.success is True
    assert res2.data["result"] == 10


def test_safe_calculate_tool_division_by_zero() -> None:
    """Verify division by zero is handled cleanly without crashing."""
    calc = SafeCalculateTool()
    res = calc.execute({"expression": "10 / 0"})
    assert res.success is False
    assert "Division by zero" in res.error


def test_safe_calculate_tool_security_rejection() -> None:
    """Verify arbitrary code injection attempts are safely rejected by AST validation."""
    calc = SafeCalculateTool()

    # Function call attempt
    res1 = calc.execute({"expression": "__import__('os').system('echo pwned')"})
    assert res1.success is False

    # Variable lookup
    res2 = calc.execute({"expression": "open('test.txt')"})
    assert res2.success is False
