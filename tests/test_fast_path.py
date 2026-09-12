"""Unit tests for Pixel Fast Path Engine and deterministic execution bypass."""

from unittest.mock import MagicMock
import pytest

from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.agent.fast_path import FastPathEngine, evaluate_math_expression
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.memory.manager import MemoryManager
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.registry import ToolRegistry


class DummyAppTool(Tool):
    def __init__(self):
        super().__init__(name="launch_application", description="Launch an application", risk_level=RiskLevel.LOW)

    def _run(self, arguments: dict) -> ToolResult:
        app = arguments.get("app_name", "")
        if app in ("notepad", "calculator", "calc"):
            return ToolResult(success=True, message=f"Launched {app}")
        return ToolResult(success=False, error=f"Unknown app {app}")


class DummyMemoryTool(Tool):
    def __init__(self):
        super().__init__(name="remember_memory", description="Store a memory", risk_level=RiskLevel.LOW)

    def _run(self, arguments: dict) -> ToolResult:
        content = arguments.get("content", "")
        return ToolResult(success=True, message=f"Saved: {content}")


class DummyRecallTool(Tool):
    def __init__(self):
        super().__init__(name="recall_memory", description="Recall memories", risk_level=RiskLevel.READ)

    def _run(self, arguments: dict) -> ToolResult:
        query = arguments.get("query", "")
        if "dog" in query or "max" in query:
            return ToolResult(success=True, data=[{"content": "Dog name is Max"}], message="Dog name is Max")
        return ToolResult(success=True, data=[], message="No memories found")


# ----------------------------------------------------------------------
# 1. Math Expression Evaluation Tests
# ----------------------------------------------------------------------

def test_safe_math_evaluation_basic():
    """Verify standard arithmetic operations."""
    assert evaluate_math_expression("25 * 4") == 100
    assert evaluate_math_expression("100 / 4") == 25
    assert evaluate_math_expression("50 + 25 - 10") == 65
    assert evaluate_math_expression("2 ** 8") == 256
    assert evaluate_math_expression("(10 + 5) * 2") == 30
    assert evaluate_math_expression("10 % 3") == 1


def test_safe_math_evaluation_functions():
    """Verify math functions (sqrt, abs, round, sin)."""
    assert evaluate_math_expression("sqrt(144)") == 12
    assert evaluate_math_expression("abs(-42)") == 42
    assert evaluate_math_expression("round(3.14159, 2)") == 3.14


def test_safe_math_evaluation_rejection_of_unsafe_code():
    """Verify that dangerous builtins and syntax are strictly rejected."""
    assert evaluate_math_expression("__import__('os').system('dir')") is None
    assert evaluate_math_expression("open('/etc/passwd')") is None
    assert evaluate_math_expression("exec('x = 1')") is None
    assert evaluate_math_expression("lambda x: x + 1") is None


def test_safe_math_zero_division():
    """Verify division by zero returns None gracefully without crashing."""
    assert evaluate_math_expression("100 / 0") is None


# ----------------------------------------------------------------------
# 2. FastPathEngine Command Matching Tests
# ----------------------------------------------------------------------

def test_fast_path_math_queries():
    """Verify various math prompt phrasing triggers deterministic calculation."""
    engine = FastPathEngine()
    assert engine.try_execute("calculate 25 * 4") == "25 * 4 = 100"
    assert engine.try_execute("what is 100 / 5?") == "100 / 5 = 20"
    assert engine.try_execute("calc 50 * 8") == "50 * 8 = 400"
    assert engine.try_execute("what's 12 + 15") == "12 + 15 = 27"


def test_fast_path_system_time_and_date():
    """Verify current time and date triggers instant response."""
    engine = FastPathEngine()
    time_res = engine.try_execute("what time is it?")
    assert time_res is not None
    assert "The current time is" in time_res

    date_res = engine.try_execute("what is today's date?")
    assert date_res is not None
    assert "Today is" in date_res


def test_fast_path_app_launch():
    """Verify app launch executes via registered launch_application tool."""
    registry = ToolRegistry()
    registry.register(DummyAppTool())
    engine = FastPathEngine(registry=registry)

    res = engine.try_execute("open notepad")
    assert res == "Successfully opened notepad."

    res_unknown = engine.try_execute("open unknownapp")
    assert "Could not launch 'unknownapp'" in res_unknown


def test_fast_path_memory_store_and_recall():
    """Verify memory operations execute deterministically."""
    registry = ToolRegistry()
    registry.register(DummyMemoryTool())
    registry.register(DummyRecallTool())
    mem_mgr = MagicMock(spec=MemoryManager)
    engine = FastPathEngine(registry=registry, memory_manager=mem_mgr)

    res_store = engine.try_execute("remember that my dog is Max")
    assert "I've remembered that: my dog is Max" in res_store

    res_recall = engine.try_execute("recall dog")
    assert "Here is what I remember about 'dog':" in res_recall
    assert "Dog name is Max" in res_recall


def test_fast_path_non_deterministic_pass_through():
    """Verify complex open-ended prompts return None to proceed to LLM."""
    engine = FastPathEngine()
    assert engine.try_execute("Write a python script to parse CSV") is None
    assert engine.try_execute("How does photosynthesis work?") is None
    assert engine.try_execute("Help me debug this error message") is None


# ----------------------------------------------------------------------
# 3. Agent Fast Path Integration Tests
# ----------------------------------------------------------------------

def test_agent_run_bypasses_llm_on_fast_path():
    """Verify agent.run() returns fast path answer without calling client.chat()."""
    registry = ToolRegistry()
    client = MagicMock(spec=OllamaClient)
    conv = Conversation()
    agent = Agent(conversation=conv, client=client, registry=registry)

    res = agent.run("calculate 125 * 8")
    assert "125 * 8 = 1000" in res
    client.chat.assert_not_called()
    assert len(conv.get_messages()) == 2  # user + assistant


def test_agent_stream_run_bypasses_llm_on_fast_path():
    """Verify agent.stream_run() yields fast path answer without calling client.stream_chat()."""
    registry = ToolRegistry()
    client = MagicMock(spec=OllamaClient)
    conv = Conversation()
    agent = Agent(conversation=conv, client=client, registry=registry)

    tokens = list(agent.stream_run("what is 50 * 5?"))
    combined = "".join(tokens)
    assert "50 * 5 = 250" in combined
    client.stream_chat.assert_not_called()
    client.chat.assert_not_called()
