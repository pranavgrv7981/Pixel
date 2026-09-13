"""PIXEL FAST CHAT V2 — Comprehensive Stage-by-Stage Profiler and Validator."""

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.agent.fast_router import FastRouter
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import FastChatProfile
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry


def get_processor_info() -> str:
    try:
        res = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            if "qwen3:4b" in line:
                return line.strip()
        return res.stdout.strip() or "No running models in VRAM"
    except Exception as e:
        return f"Error: {e}"


def run_comprehensive_benchmark():
    settings = Settings(
        fast_model="qwen3:4b",
        fast_chat_think=False,
        fast_num_ctx=2048,
        fast_num_predict=256,
        fast_temperature=0.3,
        fast_keep_alive="30m",
        enable_fast_path=True,
    )
    client = OllamaClient(settings=settings)
    tool_reg = ToolRegistry()
    perm_mgr = PermissionManager(settings=settings)
    model_reg = ModelRegistry(settings=settings)
    avail = ModelAvailabilityChecker(client=client)
    router = ModelRouter(registry=model_reg, availability_checker=avail, settings=settings)

    test_queries = [
        ("Hello, who are you?", "Casual Greeting"),
        ("Explain the difference between synchronous and asynchronous code in 2 sentences", "Explanatory Query"),
    ]

    print("=" * 110)
    print("PIXEL FAST CHAT V2 — COMPREHENSIVE 10-STAGE LATENCY BREAKDOWN & VERIFICATION")
    print("=" * 110)

    for prompt, category_label in test_queries:
        print(f"\nTarget Query: '{prompt}' ({category_label})")
        print("-" * 110)

        # Stage 1: FastRouter Latency
        t0 = time.perf_counter()
        fast_decision = FastRouter.route(prompt)
        t_fast_router_ms = (time.perf_counter() - t0) * 1000.0

        print(f"[*] Stage 1 (FastRouter): Intent='{fast_decision.intent}', Confidence={fast_decision.confidence:.2f}, Latency={t_fast_router_ms:.3f}ms")
        print(f"    - Requires Tools: {fast_decision.requires_tools}")
        print(f"    - Requires Memory: {fast_decision.requires_memory}")
        print(f"    - Requires RAG: {fast_decision.requires_rag}")
        print(f"    - Suggested Tier: {fast_decision.suggested_tier}")

        trials_data = []

        for trial in range(5):
            conv = Conversation()
            agent = Agent(
                client=client,
                conversation=conv,
                registry=tool_reg,
                permission_manager=perm_mgr,
                router=router,
                settings=settings,
            )

            # Stage 2: Intent Analysis & Model Routing
            t_route_start = time.perf_counter()
            intent = agent.intent_analyzer.analyze(prompt)
            routing_decision = router.route_request(prompt)
            t_routing_ms = (time.perf_counter() - t_route_start) * 1000.0

            # Stage 3: Prompt & Context Assembly
            t_ctx_start = time.perf_counter()
            # For casual/direct chat, no memory DB lookup or tools schema
            payload = conv.get_messages_for_llm()
            payload.append({"role": "user", "content": prompt})
            serialized_payload = json.dumps(payload)
            payload_bytes = len(serialized_payload.encode("utf-8"))
            t_ctx_ms = (time.perf_counter() - t_ctx_start) * 1000.0

            # Stage 4: Input Token Count
            input_tokens = max(1, len(prompt) // 4)

            # Stage 5-10: Ollama Execution with Metadata Capture
            t_stream_start = time.perf_counter()
            first_chunk_t = None
            chunks = []
            final_meta = {}

            # Stream via Agent
            for chunk in agent.stream_run(prompt, interactive=False):
                now = time.perf_counter()
                if first_chunk_t is None:
                    first_chunk_t = now
                chunks.append(chunk)

            t_stream_end = time.perf_counter()

            ttft_ms = ((first_chunk_t - t_stream_start) * 1000.0) if first_chunk_t else 0.0
            gen_duration_ms = ((t_stream_end - first_chunk_t) * 1000.0) if first_chunk_t else 0.0
            total_turn_ms = (t_stream_end - t_stream_start) * 1000.0

            full_resp = "".join(chunks)
            out_tokens = max(1, len(full_resp) // 4)
            tok_per_sec = (out_tokens / (gen_duration_ms / 1000.0)) if gen_duration_ms > 0 else 0.0

            trial_record = {
                "trial": trial + 1,
                "is_cold": trial == 0,
                "fast_router_ms": t_fast_router_ms,
                "routing_ms": t_routing_ms,
                "selected_model": routing_decision.selected_model,
                "context_ms": t_ctx_ms,
                "serialized_bytes": payload_bytes,
                "input_tokens": input_tokens,
                "ttft_ms": ttft_ms,
                "gen_duration_ms": gen_duration_ms,
                "total_turn_ms": total_turn_ms,
                "chunks_count": len(chunks),
                "output_tokens": out_tokens,
                "tokens_per_sec": tok_per_sec,
                "response_sample": full_resp[:80].replace("\n", " "),
            }
            trials_data.append(trial_record)

            run_type = "COLD" if trial == 0 else f"WARM #{trial}"
            print(f"[{run_type}] TTFT={ttft_ms:.1f}ms | Generation={gen_duration_ms:.1f}ms ({len(chunks)} chunks, {tok_per_sec:.1f} tok/s) | Total={total_turn_ms:.1f}ms")
            safe_resp = trial_record['response_sample'].encode('ascii', errors='replace').decode('ascii')
            print(f"       Response: {safe_resp}")

        # Summary Metrics
        all_ttfts = [t["ttft_ms"] for t in trials_data]
        all_totals = [t["total_turn_ms"] for t in trials_data]
        warm_ttfts = [t["ttft_ms"] for t in trials_data[1:]]
        warm_totals = [t["total_turn_ms"] for t in trials_data[1:]]

        print(f"\nSUMMARY METRICS for '{prompt}':")
        print(f"  - Selected Model: {trials_data[0]['selected_model']}")
        print(f"  - Processor / Hardware Offload: {get_processor_info()}")
        print(f"  - Cold Run: TTFT = {all_ttfts[0]:.1f}ms, Total = {all_totals[0]:.1f}ms")
        print(f"  - Warm Median TTFT: {statistics.median(warm_ttfts):.1f}ms (P95: {sorted(warm_ttfts)[-1]:.1f}ms)")
        print(f"  - Warm Median Total: {statistics.median(warm_totals):.1f}ms (P95: {sorted(warm_totals)[-1]:.1f}ms)")
        print(f"  - FastRouter Latency: {t_fast_router_ms:.3f}ms")
        print(f"  - Context Assembly Latency: {trials_data[0]['context_ms']:.3f}ms ({trials_data[0]['serialized_bytes']} bytes)")


if __name__ == "__main__":
    run_comprehensive_benchmark()
