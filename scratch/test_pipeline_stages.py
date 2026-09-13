"""Stage-by-stage instrumentation for the 10 critical pipeline stages."""

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.agent.fast_router import FastRouter
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import FastChatProfile, ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry


def run_stage_profiling():
    settings = Settings(
        fast_model="qwen3:4b",
        fast_chat_think=False,
        fast_num_ctx=2048,
        fast_num_predict=384,
        fast_temperature=0.4,
        fast_keep_alive="30m",
        enable_fast_path=True,
    )
    client = OllamaClient(settings=settings)
    tool_reg = ToolRegistry()
    perm_mgr = PermissionManager(settings=settings)
    model_reg = ModelRegistry(settings=settings)
    avail = ModelAvailabilityChecker(client=client)
    router = ModelRouter(registry=model_reg, availability_checker=avail, settings=settings)

    prompts = [
        "Hello, who are you?",
        "Explain the difference between synchronous and asynchronous code in 2 sentences",
    ]

    for prompt in prompts:
        print("\n" + "=" * 80)
        print(f"STAGE-BY-STAGE PROFILE FOR: '{prompt}'")
        print("=" * 80)

        runs = []
        for trial in range(5):
            stage_times = {}

            # Stage 1: FastRouter latency
            t0 = time.perf_counter()
            fast_decision = FastRouter.route(prompt)
            t1 = time.perf_counter()
            stage_times["1_fast_router_ms"] = (t1 - t0) * 1000.0

            # Stage 2: Intent Analyzer & Model Router
            conv = Conversation()
            agent = Agent(
                client=client,
                conversation=conv,
                registry=tool_reg,
                permission_manager=perm_mgr,
                router=router,
                settings=settings,
            )
            t2 = time.perf_counter()
            intent = agent.intent_analyzer.analyze(prompt)
            routing = router.route_request(prompt)
            t3 = time.perf_counter()
            stage_times["2_intent_model_routing_ms"] = (t3 - t2) * 1000.0

            # Stage 3: Prompt & Context Construction + Serialized Size
            t4 = time.perf_counter()
            payload = conv.get_messages_for_llm()
            payload.append({"role": "user", "content": prompt})
            serialized_payload = json.dumps(payload)
            payload_bytes = len(serialized_payload.encode("utf-8"))
            t5 = time.perf_counter()
            stage_times["3_context_construction_ms"] = (t5 - t4) * 1000.0
            stage_times["3_serialized_bytes"] = payload_bytes

            # Stage 4: Input Token Count estimate
            input_token_est = max(1, len(prompt) // 4)
            stage_times["4_input_token_est"] = input_token_est

            # Stage 5-10: Ollama Streaming Execution
            t_stream_start = time.perf_counter()
            t_http_connected = None
            t_first_token = None
            chunks = []
            final_meta = {}

            fast_profile = FastChatProfile(model=routing.selected_model)
            stream_gen = client.stream_chat(
                payload,
                model=routing.selected_model,
                options=fast_profile.to_ollama_options(),
                think=False,
            )

            for chunk in stream_gen:
                now = time.perf_counter()
                if t_first_token is None:
                    t_first_token = now
                chunks.append(chunk)

            t_stream_end = time.perf_counter()

            ttft_ms = ((t_first_token - t_stream_start) * 1000.0) if t_first_token else 0.0
            gen_duration_ms = ((t_stream_end - t_first_token) * 1000.0) if t_first_token else 0.0
            total_duration_ms = (t_stream_end - t_stream_start) * 1000.0

            stage_times["5_ttft_ms"] = ttft_ms
            stage_times["6_gen_duration_ms"] = gen_duration_ms
            stage_times["7_total_stream_ms"] = total_duration_ms
            stage_times["8_chunks_count"] = len(chunks)
            stage_times["9_response_preview"] = "".join(chunks)[:60].replace("\n", " ")

            runs.append(stage_times)

            print(f"Trial {trial+1}: Router={stage_times['1_fast_router_ms']:.2f}ms | Context={stage_times['3_context_construction_ms']:.2f}ms ({payload_bytes}B) | TTFT={ttft_ms:.1f}ms | Gen={gen_duration_ms:.1f}ms ({len(chunks)} chunks) | Total={total_duration_ms:.1f}ms")
            safe_preview = stage_times['9_response_preview'].encode('ascii', errors='replace').decode('ascii')
            print(f"         Preview: {safe_preview}")

        # Summary for prompt
        ttfts = [r["5_ttft_ms"] for r in runs]
        gens = [r["6_gen_duration_ms"] for r in runs]
        totals = [r["7_total_stream_ms"] for r in runs]
        print(f"\nSummary for '{prompt}':")
        print(f"  Cold Run (Trial 1): TTFT={ttfts[0]:.1f}ms, Total={totals[0]:.1f}ms")
        print(f"  Warm Runs (Trials 2-5): Median TTFT={statistics.median(ttfts[1:]):.1f}ms, P95 TTFT={sorted(ttfts[1:])[3]:.1f}ms")
        print(f"  Overall Median Total: {statistics.median(totals):.1f}ms")


if __name__ == "__main__":
    run_stage_profiling()
