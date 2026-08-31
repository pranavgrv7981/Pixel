"""Harmless demo and testing tools."""

import ast
from datetime import datetime
import operator
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.tools.base import RiskLevel, Tool, ToolResult


class GetCurrentTimeArgs(BaseModel):
    """Parameters for get_current_time."""

    format: Optional[str] = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="Optional strftime format string (default: '%Y-%m-%d %H:%M:%S')",
    )


class GetCurrentTimeTool(Tool):
    """Harmless demo tool that retrieves the current system date and time."""

    def __init__(self) -> None:
        super().__init__(
            name="get_current_time",
            description="Retrieve the current local date and time.",
            risk_level=RiskLevel.READ,
            args_model=GetCurrentTimeArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        fmt = args.get("format") or "%Y-%m-%d %H:%M:%S"
        try:
            now_str = datetime.now().strftime(fmt)
            return ToolResult(
                success=True,
                data={"current_time": now_str, "format": fmt},
                message=f"The current time is {now_str}",
            )
        except Exception as err:
            return ToolResult(
                success=False,
                error=f"Invalid time format string '{fmt}': {err}",
            )


class CalculateArgs(BaseModel):
    """Parameters for calculate tool."""

    expression: str = Field(description="Arithmetic expression to safely evaluate, e.g. '2 + 2' or '10 * (5 + 3)'")


# Supported AST operators for safe calculation (no eval)
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_node(node: ast.AST) -> float:
    """Recursively evaluate an AST expression using only allowed arithmetic operations."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        op_type = type(node.op)
        if op_type in _SAFE_OPERATORS:
            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise ZeroDivisionError("Division by zero in calculation")
            return float(_SAFE_OPERATORS[op_type](left, right))
        raise ValueError(f"Unsupported operator: {op_type.__name__}")

    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval_node(node.operand)
        op_type = type(node.op)
        if op_type in _SAFE_OPERATORS:
            return float(_SAFE_OPERATORS[op_type](operand))
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")

    raise ValueError(f"Unsupported AST expression node: {type(node).__name__}")


class SafeCalculateTool(Tool):
    """Safely evaluates arithmetic math expressions without using unrestricted eval()."""

    def __init__(self) -> None:
        super().__init__(
            name="calculate",
            description="Safely evaluate basic arithmetic expressions (e.g. '25 * 4', '(10 + 2) / 3').",
            risk_level=RiskLevel.READ,
            args_model=CalculateArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        expr = args.get("expression", "").strip()
        if not expr:
            return ToolResult(success=False, error="Expression cannot be empty")

        try:
            parsed = ast.parse(expr, mode="eval")
            result = _safe_eval_node(parsed.body)
            # Format integer results cleanly if whole number
            formatted = int(result) if result.is_integer() else result
            return ToolResult(
                success=True,
                data={"expression": expr, "result": formatted},
                message=f"The result of {expr} is {formatted}",
            )
        except Exception as err:
            return ToolResult(
                success=False,
                error=f"Calculation error: {err}",
            )


class DemoMediumRiskArgs(BaseModel):
    """Parameters for demo_medium_risk_tool."""

    action_name: str = Field(description="Name of the demo action to simulate")


class DemoMediumRiskTool(Tool):
    """Harmless demo tool with MEDIUM risk level used to verify user confirmation workflows."""

    def __init__(self) -> None:
        super().__init__(
            name="demo_medium_risk_tool",
            description="Harmless simulation tool with MEDIUM risk level to test approval confirmations.",
            risk_level=RiskLevel.MEDIUM,
            args_model=DemoMediumRiskArgs,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action_name", "unnamed_action")
        return ToolResult(
            success=True,
            data={"simulated_action": action, "status": "completed"},
            message=f"Simulated medium-risk action '{action}' executed successfully after approval.",
        )

