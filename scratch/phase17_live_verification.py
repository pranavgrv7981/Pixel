"""Comprehensive Phase 17 live verification script."""

import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.agent.agent import Agent
from app.core.config import get_settings
from app.core.ollama_client import OllamaClient
from app.context.database import ContextDatabase
from app.context.manager import ContextManager
from app.context.models import ResponseStyle
from app.knowledge.manager import KnowledgeManager
from app.memory.manager import MemoryManager
from app.models.router import ModelRouter
from app.tools.registry import ToolRegistry
from app.tools.demo import SafeCalculateTool, GetCurrentTimeTool


def run_live_verification():
    print("======================================================================")
    print("  PHASE 17 LIVE VERIFICATION SUITE")
    print("======================================================================")

    settings = get_settings()
    client = OllamaClient(settings=settings)
    memory_mgr = MemoryManager(settings=settings)
    memory_mgr.initialize()
    knowledge_mgr = KnowledgeManager(settings=settings)
    knowledge_mgr.initialize()

    context_mgr = ContextManager(
        memory_manager=memory_mgr,
        knowledge_manager=knowledge_mgr,
        settings=settings,
    )
    context_mgr.initialize()

    registry = ToolRegistry()
    registry.register(SafeCalculateTool())
    registry.register(GetCurrentTimeTool())

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

    agent = Agent(
        client=client,
        registry=registry,
        memory_manager=memory_mgr,
        router=router,
        context_manager=context_mgr,
        settings=settings,
    )

    # -------------------------------------------------------------------------
    # Test 1: Simple Chat ("hi")
    # -------------------------------------------------------------------------
    print("\n--- [TEST 1] Simple Chat ('hi') ---")
    start = time.perf_counter()
    resp_tokens = []
    for token in agent.stream_run("hi"):
        resp_tokens.append(token)
    elapsed = time.perf_counter() - start
    print(f"Response: {''.join(resp_tokens).strip()}")
    print(f"Elapsed: {elapsed:.2f}s")
    diag = context_mgr.get_last_diagnostics()
    if diag:
        print(f"Context Diagnostics: {diag.included_items_count} items ({diag.estimated_tokens} tokens), latency: {diag.latency_ms:.2f}ms")
    assert len(resp_tokens) > 0, "No tokens generated for simple chat"

    # -------------------------------------------------------------------------
    # Test 2: Memory Context ("What is my main project?")
    # -------------------------------------------------------------------------
    print("\n--- [TEST 2] Memory Context ---")
    memory_mgr.remember(category="project", key="main_project", value="Atlas", importance=5)
    memory_mgr.remember(category="personal_fact", key="favorite_food", value="Sushi", importance=3)

    resp_mem = agent.run("What is my main project?")
    print(f"Response: {resp_mem.strip()}")
    diag_mem = context_mgr.get_last_diagnostics()
    if diag_mem:
        print(f"Source Breakdown: {diag_mem.source_breakdown}")
        assert diag_mem.source_breakdown.get("memory", 0) >= 1, "Memory source should be included"

    # -------------------------------------------------------------------------
    # Test 3: RAG Knowledge Context
    # -------------------------------------------------------------------------
    print("\n--- [TEST 3] RAG Knowledge Context ---")
    doc_path = settings.get_resolved_data_dir() / "knowledge_test.txt"
    doc_path.write_text("The secret project codename is Project Chronos. It handles time dilation algorithms.", encoding="utf-8")
    knowledge_mgr.index_file(doc_path)

    resp_rag = agent.run("What is the codename of the project that handles time dilation?")
    print(f"Response: {resp_rag.strip()}")
    diag_rag = context_mgr.get_last_diagnostics()
    if diag_rag:
        print(f"Source Breakdown: {diag_rag.source_breakdown}")
        assert diag_rag.source_breakdown.get("knowledge", 0) >= 1, "Knowledge source should be included"

    # -------------------------------------------------------------------------
    # Test 4: System Metrics Query
    # -------------------------------------------------------------------------
    print("\n--- [TEST 4] System Metrics Query ---")
    resp_sys = agent.run("What is my current RAM usage?")
    print(f"Response: {resp_sys.strip()}")
    diag_sys = context_mgr.get_last_diagnostics()
    if diag_sys:
        print(f"Source Breakdown: {diag_sys.source_breakdown}")
        assert diag_sys.source_breakdown.get("system", 0) >= 1, "System source should be included"

    # -------------------------------------------------------------------------
    # Test 5: Personalization (Concise vs Detailed)
    # -------------------------------------------------------------------------
    print("\n--- [TEST 5] Personalization Response Style ---")
    context_mgr.profile_manager.update_profile(response_style=ResponseStyle.CONCISE)
    resp_concise = agent.run("Explain recursion in one sentence.")
    print(f"Concise Response: {resp_concise.strip()}")

    context_mgr.profile_manager.update_profile(response_style=ResponseStyle.BALANCED)

    # -------------------------------------------------------------------------
    # Test 6: Project Context
    # -------------------------------------------------------------------------
    print("\n--- [TEST 6] Project Context ---")
    context_mgr.project_manager.set_active_project(
        project_name="Phase 17 Verification Workspace",
        root_path=str(settings.project_root),
        primary_language="Python",
        description="Testing Phase 17 Context Management Subsystem",
    )
    resp_proj = agent.run("What project am I currently working on?")
    print(f"Response: {resp_proj.strip()}")
    diag_proj = context_mgr.get_last_diagnostics()
    if diag_proj:
        print(f"Source Breakdown: {diag_proj.source_breakdown}")
        assert diag_proj.source_breakdown.get("project_context", 0) >= 1, "Project context source should be included"

    # -------------------------------------------------------------------------
    # Test 7: Tool Regression (Calculate 25 * 4)
    # -------------------------------------------------------------------------
    print("\n--- [TEST 7] Tool Calling Regression (Calculate 25 * 4) ---")
    resp_calc = agent.run("What is 25 * 4?")
    print(f"Response: {resp_calc.strip()}")
    assert "100" in resp_calc, "Tool calculate failed to answer 100"

    print("\n======================================================================")
    print("  ALL PHASE 17 LIVE TESTS COMPLETED SUCCESSFULLY!")
    print("======================================================================")


if __name__ == "__main__":
    run_live_verification()
