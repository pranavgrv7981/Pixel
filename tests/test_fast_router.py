"""Unit tests for confidence-based FastRouter."""

from app.agent.fast_router import FastRouteDecision, FastRouter


def test_fast_router_empty_prompt():
    res = FastRouter.route("")
    assert res.intent == "empty"
    assert res.is_deterministic is True
    assert res.confidence == 1.0


def test_fast_router_time_and_date():
    res_time = FastRouter.route("what time is it?")
    assert res_time.intent == "time"
    assert res_time.is_deterministic is True
    assert res_time.confidence == 1.0
    assert res_time.suggested_tier == "DIRECT"

    res_date = FastRouter.route("what is today's date")
    assert res_date.intent == "date"
    assert res_date.is_deterministic is True
    assert res_date.confidence == 1.0


def test_fast_router_math_expressions():
    res1 = FastRouter.route("calculate 25 * 4")
    assert res1.intent == "math"
    assert res1.is_deterministic is True
    assert res1.confidence >= 0.95
    assert res1.arguments.get("expression") == "25 * 4"

    res2 = FastRouter.route("what is 100 / 4 + 15?")
    assert res2.intent == "math"
    assert res2.is_deterministic is True


def test_fast_router_app_launch():
    res = FastRouter.route("open notepad")
    assert res.intent == "app_launch"
    assert res.is_deterministic is True
    assert res.confidence >= 0.95
    assert res.arguments.get("app_name") == "notepad"

    res_calc = FastRouter.route("launch calculator")
    assert res_calc.intent == "app_launch"
    assert res_calc.is_deterministic is True


def test_fast_router_memory_store_and_recall():
    res_store = FastRouter.route("remember that my favorite color is teal")
    assert res_store.intent == "memory_store"
    assert res_store.is_deterministic is True
    assert res_store.requires_memory is True

    res_recall = FastRouter.route("recall favorite color")
    assert res_recall.intent == "memory_recall"
    assert res_recall.is_deterministic is True
    assert res_recall.requires_memory is True


def test_fast_router_casual_chat_pruning():
    """Verify casual chat turns do not activate tools or memory lookups."""
    res_hi = FastRouter.route("hi")
    assert res_hi.intent == "casual_chat"
    assert res_hi.is_deterministic is False
    assert res_hi.requires_tools is False
    assert res_hi.requires_memory is False
    assert res_hi.requires_rag is False
    assert res_hi.suggested_tier == "FAST_MODEL"

    res_hello = FastRouter.route("Hello, how are you doing?")
    assert res_hello.intent == "casual_chat"
    assert res_hello.requires_tools is False
    assert res_hello.requires_memory is False
    assert res_hello.requires_rag is False


def test_fast_router_complex_tool_requests():
    """Verify tool requests are flagged to include tools and standard/heavy tiers."""
    res_code = FastRouter.route("Please read file config.py and execute tests")
    assert res_code.is_deterministic is False
    assert res_code.requires_tools is True
    assert res_code.suggested_tier in ("STANDARD", "HEAVY")
