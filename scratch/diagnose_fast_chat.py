"""Comprehensive diagnostic and profiling script for Pixel Fast Chat V2.
Measures each stage of the pipeline independently with cold and warm runs.
"""

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
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry


def check_ollama_ps() -> str:
    try:
        res = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except Exception as e:
        return f"Error running ollama ps: {e}"


def profile_direct_ollama_api(prompt: str, think_param: bool = False, system_prompt: Optional[str] = None):
    url = "http://localhost:11434/api/chat"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": "qwen3:4b",
        "messages": messages,
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "num_predict": 384,
            "temperature": 0.4,
        },
        "keep_alive": "30m",
    }
    if not think_param:
        payload["think"] = False

    t_start = time.perf_counter()
    first_token_t = None
    first_visible_token_t = None
    chunks = []
    tokens = []
    final_metadata = {}

    with httpx.Client(timeout=120.0) as client:
        t_req_start = time.perf_counter()
        with client.stream("POST", url, json=payload) as response:
            t_connected = time.perf_counter()
            for line in response.iter_lines():
                if not line:
                    continue
                chunk_json = json.loads(line)
                now = time.perf_counter()
                if first_token_t is None:
                    first_token_t = now

                content = chunk_json.get("message", {}).get("content", "")
                if content:
                    tokens.append((now - t_start, content))
                    if first_visible_token_t is None and not content.startswith("<think>"):
                        first_visible_token_t = now

                if chunk_json.get("done", False):
                    final_metadata = chunk_json

    t_end = time.perf_counter()
    total_duration = t_end - t_start
    http_startup = t_connected - t_req_start
    ttft_raw = (first_token_t - t_start) if first_token_t else None
    ttft_visible = (first_visible_token_t - t_start) if first_visible_token_t else None

    return {
        "total_duration_s": total_duration,
        "http_startup_s": http_startup,
        "ttft_raw_s": ttft_raw,
        "ttft_visible_s": ttft_visible,
        "tokens": tokens,
        "metadata": final_metadata,
        "full_text": "".join(t[1] for t in tokens),
    }


def run_diagnostics():
    print("=" * 80)
    print("PIXEL FAST CHAT V2 — DIAGNOSTIC & PROFILING RUN")
    print("=" * 80)

    print("\n[1] Initial Ollama State:")
    print(check_ollama_ps())

    prompts = [
        ("Hello, who are you?", "Casual Greeting"),
        ("Explain the difference between synchronous and asynchronous code in 2 sentences", "Explanatory Prompt"),
    ]

    router = FastRouter()

    for prompt, label in prompts:
        print(f"\n" + "=" * 60)
        print(f"PROFILING: '{prompt}' ({label})")
        print("=" * 60)

        # 1. FastRouter profiling
        t0 = time.perf_counter()
        decision = router.route(prompt)
        t_router = (time.perf_counter() - t0) * 1000.0
        print(f"1. FastRouter Decision: intent={decision.intent}, conf={decision.confidence:.2f}, req_tools={decision.requires_tools}, req_mem={decision.requires_memory} (Time: {t_router:.3f}ms)")

        # 2. Direct Ollama API Profiling (5 repetitions to get cold/warm stats)
        print("\nRunning 5 repetitions via direct HTTP API to Ollama:")
        runs = []
        for i in range(5):
            res = profile_direct_ollama_api(prompt, think_param=False)
            meta = res["metadata"]
            total_dur_ms = res["total_duration_s"] * 1000.0
            ttft_raw_ms = (res["ttft_raw_s"] * 1000.0) if res["ttft_raw_s"] else 0.0
            ttft_vis_ms = (res["ttft_visible_s"] * 1000.0) if res["ttft_visible_s"] else 0.0
            load_dur_ms = meta.get("load_duration", 0) / 1e6
            prompt_eval_dur_ms = meta.get("prompt_eval_duration", 0) / 1e6
            prompt_eval_count = meta.get("prompt_eval_count", 0)
            eval_dur_ms = meta.get("eval_duration", 0) / 1e6
            eval_count = meta.get("eval_count", 0)

            runs.append({
                "rep": i + 1,
                "total_ms": total_dur_ms,
                "ttft_raw_ms": ttft_raw_ms,
                "ttft_vis_ms": ttft_vis_ms,
                "load_dur_ms": load_dur_ms,
                "prompt_eval_dur_ms": prompt_eval_dur_ms,
                "prompt_eval_count": prompt_eval_count,
                "eval_dur_ms": eval_dur_ms,
                "eval_count": eval_count,
                "first_few_tokens": [t[1] for t in res["tokens"][:5]],
            })
            print(f"  Rep {i+1}: Total={total_dur_ms:.1f}ms | TTFT_raw={ttft_raw_ms:.1f}ms | TTFT_vis={ttft_vis_ms:.1f}ms | Load={load_dur_ms:.1f}ms | PromptEval={prompt_eval_dur_ms:.1f}ms ({prompt_eval_count} tokens) | Eval={eval_dur_ms:.1f}ms ({eval_count} tokens)")
            if i == 0:
                print(f"    First 5 tokens: {[t[1] for t in res['tokens'][:5]]}")
                print(f"    Ollama PS state: {check_ollama_ps()}")

        # Summary statistics
        raw_ttfts = [r["ttft_raw_ms"] for r in runs]
        vis_ttfts = [r["ttft_vis_ms"] for r in runs]
        totals = [r["total_ms"] for r in runs]
        print(f"\n  >> Raw TTFT: Median={statistics.median(raw_ttfts):.1f}ms | P95={sorted(raw_ttfts)[4]:.1f}ms | Cold={raw_ttfts[0]:.1f}ms | Warm={statistics.median(raw_ttfts[1:]):.1f}ms")
        print(f"  >> Visible TTFT: Median={statistics.median(vis_ttfts):.1f}ms | P95={sorted(vis_ttfts)[4]:.1f}ms | Cold={vis_ttfts[0]:.1f}ms | Warm={statistics.median(vis_ttfts[1:]):.1f}ms")
        print(f"  >> Total: Median={statistics.median(totals):.1f}ms | P95={sorted(totals)[4]:.1f}ms")


if __name__ == "__main__":
    run_diagnostics()
