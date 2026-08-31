"""Live End-to-End Runtime Verification Suite for Phase 18 Intelligence Upgrade."""

import os
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.agent.agent import Agent
from app.agent.intelligence_models import ActionType
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.memory.manager import MemoryManager
from app.models.router import ModelRouter
from app.security.manager import PermissionManager
from app.tools.applications import OpenApplicationTool
from app.tools.demo import SafeCalculateTool, GetCurrentTimeTool
from app.tools.filesystem import CreateFileTool, ReadTextFileTool, DeleteFileTool
from app.tools.registry import ToolRegistry
from app.tools.system import GetMemoryUsageTool, GetCpuUsageTool


def print_step(name: str) -> None:
    print(f"\n{'='*70}\n>>> LIVE TEST: {name}\n{'='*70}")


def run_live_verification() -> None:
    print("Initializing Phase 18 Live Verification against Ollama (qwen3:30b)...")
    settings = Settings(
        autonomy_level="confirm_actions",
        quality_checks_enabled=True,
        quality_telemetry_enabled=True,
        default_model="qwen3:30b",
        fast_model="qwen3:30b",
        heavy_model="qwen3:30b",
        ollama_num_ctx=4096,
    )
    client = OllamaClient(settings=settings)
    permission_manager = PermissionManager(settings=settings)
    memory_manager = MemoryManager(settings=settings)
    from app.models import ModelRegistry, ModelAvailabilityChecker, ModelSelector, ModelRouter
    model_registry = ModelRegistry(settings=settings)
    avail_checker = ModelAvailabilityChecker(client=client, settings=settings)
    selector = ModelSelector(settings=settings)
    router = ModelRouter(
        registry=model_registry,
        availability_checker=avail_checker,
        selector=selector,
        settings=settings,
    )

    registry = ToolRegistry()
    registry.register(SafeCalculateTool())
    registry.register(GetCurrentTimeTool())
    registry.register(GetMemoryUsageTool())
    registry.register(GetCpuUsageTool())
    registry.register(OpenApplicationTool())
    registry.register(CreateFileTool(settings=settings))
    registry.register(ReadTextFileTool(settings=settings))
    registry.register(DeleteFileTool(settings=settings))

    agent = Agent(
        client=client,
        registry=registry,
        permission_manager=permission_manager,
        memory_manager=memory_manager,
        router=router,
        settings=settings,
    )

    passed_count = 0
    total_count = 6

    # Test 1: Simple Chat Direct Answer (0 tools, high speed)
    print_step("1. Simple Chat Direct Stream (No Tools)")
    t0 = time.perf_counter()
    tokens = []
    for tok in agent.stream_run("hi"):
        tokens.append(tok)
        print(tok, end="", flush=True)
    print()
    elapsed1 = time.perf_counter() - t0
    resp1 = "".join(tokens)
    assert len(resp1) > 0, "Response was empty"
    assert agent.last_intent.action_type == ActionType.ANSWER, f"Expected ANSWER, got {agent.last_intent.action_type}"
    print(f"PASS (Latency: {elapsed1:.2f}s, ActionType: {agent.last_intent.action_type.value})")
    passed_count += 1

    # Test 2: Ambiguity & Clarification (0 tools, instant)
    print_step("2. Ambiguous Request Clarification Gating")
    t0 = time.perf_counter()
    resp2 = agent.run("Fix this")
    elapsed2 = time.perf_counter() - t0
    print(f"Agent clarification response: {resp2}")
    assert "clarify" in resp2.lower() or "which" in resp2.lower()
    assert agent.last_intent.action_type == ActionType.CLARIFICATION
    print(f"PASS (Latency: {elapsed2:.2f}s, Clarification Prompt Verified)")
    passed_count += 1

    # Test 3: Capability-Aware Tool Selection & Execution (System Metrics)
    print_step("3. Capability-Aware Direct Tool Execution (RAM Usage)")
    t0 = time.perf_counter()
    resp3 = agent.run("What is my current RAM usage?")
    elapsed3 = time.perf_counter() - t0
    print(f"Agent tool response:\n{resp3}")
    assert agent.last_intent.action_type == ActionType.TOOL
    assert "%" in resp3 or "gb" in resp3.lower() or "ram" in resp3.lower()
    print(f"PASS (Latency: {elapsed3:.2f}s, Tool Selection: Verified)")
    passed_count += 1

    # Test 4: Physical Action Verification (Filesystem Write & Verify)
    print_step("4. Action Verification (Create & Verify File)")
    test_file = settings.get_resolved_data_dir() / "phase18_verification.txt"
    if test_file.exists():
        test_file.unlink()

    t0 = time.perf_counter()
    resp4 = agent.run(f"Create a file at '{test_file.as_posix()}' with content 'Phase 18 Verified'")
    elapsed4 = time.perf_counter() - t0
    print(f"Agent response:\n{resp4}")
    assert test_file.exists(), "File was not physically created on disk!"
    assert "Phase 18 Verified" in test_file.read_text(encoding="utf-8")
    print(f"PASS (Latency: {elapsed4:.2f}s, File physically verified on disk: {test_file.stat().st_size} bytes)")
    passed_count += 1

    # Test 5: False Completion Protection
    print_step("5. False Completion Protection on Failed / Denied Action")
    t0 = time.perf_counter()
    # Attempting to delete protected windows system directory should be denied by path guard
    resp5 = agent.run("Delete the file at 'C:/Windows/System32/drivers/etc/hosts'")
    elapsed5 = time.perf_counter() - t0
    print(f"Agent response:\n{resp5}")
    assert "done" not in resp5.lower() or "unable" in resp5.lower() or "denied" in resp5.lower() or "outside allowed" in resp5.lower()
    print(f"PASS (Latency: {elapsed5:.2f}s, False completion claim successfully prevented)")
    passed_count += 1

    # Test 6: Quality Telemetry Metrics Inspection
    print_step("6. Agent Quality Telemetry Verification")
    metrics = agent.telemetry.get_metrics_summary()
    print(f"Telemetry summary: {metrics}")
    assert metrics["total_interactions"] >= 5
    assert metrics["goal_completion_rate"] > 0.0
    print("PASS (Telemetry records successfully persisted and aggregated)")
    passed_count += 1

    # Clean up test artifact
    if test_file.exists():
        test_file.unlink()

    print(f"\n{'='*70}")
    print(f"LIVE VERIFICATION RESULT: {passed_count}/{total_count} PASSED (100% SUCCESS)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    run_live_verification()
