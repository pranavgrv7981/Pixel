"""Pixel Fast Path Engine for deterministic command evaluation without LLM invocation."""

import ast
import datetime
import math
import operator
import re
from typing import Any, Callable, Optional

from app.core.logging import get_logger
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry

logger = get_logger("agent.fast_path")

# Safe math operators
_SAFE_OPERATORS: dict[type, Callable[..., Any]] = {
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

_SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval_node(node: ast.AST) -> Any:
    """Recursively evaluate an AST expression using only safe mathematical operations."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Non-numeric constant in math expression")
    elif isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCTIONS:
            return _SAFE_FUNCTIONS[node.id]
        raise ValueError(f"Unknown symbol: {node.id}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero")
        if op_type == ast.Pow and (right > 100 or left > 10000):
            raise OverflowError("Exponent too large")
        return _SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _safe_eval_node(node.operand)
        return _SAFE_OPERATORS[op_type](operand)
    elif isinstance(node, ast.Call):
        func = _safe_eval_node(node.func)
        if not callable(func):
            raise ValueError("Expression is not callable")
        args = [_safe_eval_node(arg) for arg in node.args]
        return func(*args)
    else:
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def evaluate_math_expression(expr: str) -> Optional[float | int]:
    """Safely evaluate a mathematical string expression."""
    clean_expr = expr.strip()
    if not clean_expr:
        return None
    try:
        parsed = ast.parse(clean_expr, mode="eval")
        result = _safe_eval_node(parsed.body)
        if isinstance(result, (int, float)):
            if isinstance(result, float) and result.is_integer():
                return int(result)
            return result
        return None
    except Exception as err:
        logger.debug("Safe math eval failed for '%s': %s", expr, err)
        return None


class FastPathEngine:
    """Evaluates deterministic user commands without calling LLM inference."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        memory_manager: Optional[Any] = None,
        permission_manager: Optional[Any] = None,
    ) -> None:
        self.registry = registry
        self.memory_manager = memory_manager
        self.permission_manager = permission_manager

    def try_execute(self, prompt: str) -> Optional[str]:
        """Attempt to resolve the prompt deterministically. Returns response string or None."""
        text = prompt.strip()
        if not text:
            return None

        # 1. System Time and Date
        res_time = self._try_system_time(text)
        if res_time is not None:
            return res_time

        # 2. Mathematical Calculations
        res_math = self._try_calculation(text)
        if res_math is not None:
            return res_math

        # 3. Application Launch
        res_app = self._try_app_launch(text)
        if res_app is not None:
            return res_app

        # 4. Memory Store & Recall
        res_mem = self._try_memory_operation(text)
        if res_mem is not None:
            return res_mem

        # 5. System Status (Battery / Disk)
        res_sys = self._try_system_status(text)
        if res_sys is not None:
            return res_sys

        return None

    def _try_system_time(self, text: str) -> Optional[str]:
        lower = text.lower().strip("?.! ")
        if lower in (
            "what time is it",
            "time",
            "current time",
            "tell me the time",
            "what is the time",
            "what's the time",
        ):
            now = datetime.datetime.now()
            return f"The current time is {now.strftime('%I:%M:%S %p')}."

        if lower in (
            "what is today's date",
            "what is the date",
            "what's the date",
            "today's date",
            "current date",
            "date",
            "what day is it",
            "what day is today",
        ):
            now = datetime.datetime.now()
            return f"Today is {now.strftime('%A, %B %d, %Y')}."

        return None

    def _try_calculation(self, text: str) -> Optional[str]:
        lower = text.lower().strip()
        # Patterns like: "calculate 25 * 4", "what is 100 / 5 + 3?", "math: 45 * 2", or direct "25 * 4"
        math_prefixes = [
            r"^calculate\s+",
            r"^what\s+is\s+",
            r"^what's\s+",
            r"^calc\s+",
            r"^math:\s*",
            r"^eval\s+",
            r"^evaluate\s+",
        ]

        candidate_expr = text
        for prefix in math_prefixes:
            match = re.search(prefix, candidate_expr, re.IGNORECASE)
            if match:
                candidate_expr = candidate_expr[match.end():]
                break

        candidate_expr = candidate_expr.strip("?.! \t\n")
        # Ensure string contains at least one math operator or math function
        has_math_chars = bool(re.search(r"[\+\-\*\/\%\^]|\b(sqrt|sin|cos|abs|round)\b", candidate_expr))
        # Ensure it does not contain non-math words
        has_invalid_words = bool(re.search(r"[a-zA-Z]{4,}", candidate_expr) and not re.search(r"\b(sqrt|round)\b", candidate_expr))

        if has_math_chars and not has_invalid_words:
            # Replace ^ with **
            sanitized = candidate_expr.replace("^", "**")
            val = evaluate_math_expression(sanitized)
            if val is not None:
                return f"{candidate_expr} = {val}"

        return None

    def _try_app_launch(self, text: str) -> Optional[str]:
        match = re.match(r"^(?:open|launch|start|run)\s+([a-zA-Z0-9_\-\. ]+)$", text.strip(), re.IGNORECASE)
        if not match:
            return None

        app_target = match.group(1).strip().lower()
        if not app_target or app_target in ("file", "files", "folder", "terminal", "url", "browser", "website", "script", "test", "python"):
            return None

        if self.registry and (self.registry.has("open_application") or self.registry.has("launch_application")):
            tool_name = "open_application" if self.registry.has("open_application") else "launch_application"
            tool = self.registry.get(tool_name)
            try:
                args = {"app_name": app_target}
                res: ToolResult = tool.execute(args)
                if res.success:
                    return f"Successfully opened {app_target}."
                else:
                    return f"Could not launch '{app_target}': {res.error or res.message or 'Application not found in whitelist.'}"
            except Exception as err:
                logger.debug("FastPath app launch failed: %s", err)
        else:
            known_apps = {"notepad", "calculator", "calc", "vscode", "code", "chrome", "edge", "paint", "mspaint", "explorer"}
            if app_target in known_apps:
                from app.tools.applications import OpenApplicationTool
                tool = OpenApplicationTool()
                try:
                    args = {"app_name": app_target}
                    res: ToolResult = tool.execute(args)
                    if res.success:
                        return f"Successfully opened {app_target}."
                except Exception as err:
                    logger.debug("FastPath fallback app launch error: %s", err)

        return None

    def _try_memory_operation(self, text: str) -> Optional[str]:
        clean = text.strip()
        # 1. Store pattern: "remember that my <key> is <value>", "remember that <key> is <value>", "remember <key> = <value>"
        store_kv_match = re.match(r"^remember\s+(?:that\s+)?(?:my\s+)?(.+?)\s+(?:is|:=|=|:)\s+(.+)$", clean, re.IGNORECASE)
        if store_kv_match:
            k = store_kv_match.group(1).strip()
            v = store_kv_match.group(2).strip()
            if k and v:
                try:
                    if self.registry and self.registry.has("remember_memory"):
                        tool = self.registry.get("remember_memory")
                        res: ToolResult = tool.execute({"key": k, "value": v, "category": "preference"})
                        stored_text = re.sub(r"^remember\s+(?:that\s+)?", "", clean, flags=re.IGNORECASE).strip()
                        if res.success:
                            return f"I've remembered that: {stored_text}"
                    elif self.memory_manager:
                        stored_text = re.sub(r"^remember\s+(?:that\s+)?", "", clean, flags=re.IGNORECASE).strip()
                        self.memory_manager.store_preference(key=k, value=v)
                        return f"I've remembered that: {stored_text}"
                except Exception as err:
                    logger.warning("FastPath memory store error: %s", err)

        store_match = re.match(r"^remember\s+(?:that\s+)?(.+)$", clean, re.IGNORECASE)
        if store_match:
            mem_content = store_match.group(1).strip()
            if mem_content:
                try:
                    if self.registry and self.registry.has("remember_memory"):
                        tool = self.registry.get("remember_memory")
                        res: ToolResult = tool.execute({"key": "user_note", "value": mem_content, "category": "general"})
                        if res.success:
                            return f"I've remembered that: {mem_content}"
                    elif self.memory_manager:
                        self.memory_manager.store_preference(key="user_note", value=mem_content)
                        return f"I've remembered that: {mem_content}"
                except Exception as err:
                    logger.warning("FastPath memory store error: %s", err)

        # 2. Recall pattern: "recall <query>", "what is my <query>", "what do you remember about <query>"
        recall_match = re.match(r"^(?:recall|what\s+is\s+my|what\s+do\s+you\s+remember\s+about)\s+([a-zA-Z0-9_\- ]+)\??$", clean, re.IGNORECASE)
        if recall_match:
            query = recall_match.group(1).strip()
            if query:
                try:
                    if self.registry and self.registry.has("recall_memory"):
                        tool = self.registry.get("recall_memory")
                        res: ToolResult = tool.execute({"query": query})
                        if res.success and res.data:
                            return f"Here is what I remember about '{query}':\n{res.message}"
                        elif res.success:
                            return f"I don't have any saved memories matching '{query}'."
                    elif self.memory_manager:
                        mems = self.memory_manager.search(query=query, limit=3)
                        if mems:
                            items = "\n".join(f"- {m.content}" for m in mems)
                            return f"Here is what I remember about '{query}':\n{items}"
                        return f"I don't have any saved memories matching '{query}'."
                except Exception as err:
                    logger.warning("FastPath memory recall error: %s", err)

        return None

    def _try_system_status(self, text: str) -> Optional[str]:
        lower = text.lower().strip("?.! ")
        if lower in ("battery", "battery status", "what is my battery level", "check battery", "battery percent"):
            if self.registry and self.registry.has("get_battery_status"):
                tool = self.registry.get("get_battery_status")
                try:
                    res: ToolResult = tool.execute({})
                    if res.success:
                        return res.message
                except Exception:
                    pass

        if lower in ("disk usage", "disk space", "check disk", "storage usage"):
            if self.registry and self.registry.has("get_disk_usage"):
                tool = self.registry.get("get_disk_usage")
                try:
                    res: ToolResult = tool.execute({})
                    if res.success:
                        return res.message
                except Exception:
                    pass

        return None
