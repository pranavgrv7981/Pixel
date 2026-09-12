import sys
import time
import statistics
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.memory.manager import MemoryManager
from app.memory.repository import MemoryRepository
from app.models.availability import ModelAvailabilityChecker
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry
from app.tools.applications import OpenApplicationTool
from app.tools.demo import GetCurrentTimeTool
from app.tools.system import GetBatteryStatusTool
from app.tools.memory import RememberMemoryTool, RecallMemoryTool


@dataclass
class BenchmarkResult:
    category: str
    prompt: str
    trials: int
    median_ttft_ms: Optional[float]
    p95_ttft_ms: Optional[float]
    median_total_ms: float
    p95_total_ms: float
    tier: str
    sample_response: str


def run_benchmarks(trials_per_case: int = 3):
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
    tool_reg.register(OpenApplicationTool(settings=settings))
    tool_reg.register(GetCurrentTimeTool())
    tool_reg.register(GetBatteryStatusTool())
    tool_reg.register(RememberMemoryTool(settings=settings))
    tool_reg.register(RecallMemoryTool(settings=settings))

    perm_mgr = PermissionManager(settings=settings)
    model_reg = ModelRegistry(settings=settings)
    avail = ModelAvailabilityChecker(client=client)
    router = ModelRouter(registry=model_reg, availability_checker=avail, settings=settings)

    test_cases = [
        ("Deterministic Arithmetic", "Calculate 125 * 8"),
        ("Deterministic System Date/Time", "What time is it?"),
        ("Deterministic App Launch", "Open notepad"),
        ("Deterministic Memory Store", "Remember that my favourite color is cerulean blue"),
        ("Deterministic Memory Recall", "What is my favourite color?"),
        ("Fast Conversational Chat", "Hello, who are you?"),
        ("Standard Knowledge Request", "Explain the difference between synchronous and asynchronous code in 2 sentences"),
    ]

    print(f"{'Category':<32} | {'Tier':<8} | {'Median TTFT':<12} | {'P95 TTFT':<10} | {'Median Total':<13} | {'P95 Total':<10}")
    print("-" * 105)

    results: list[BenchmarkResult] = []

    for cat_name, prompt in test_cases:
        ttft_samples: list[float] = []
        total_samples: list[float] = []
        last_resp = ""
        tier_label = "UNKNOWN"

        for trial in range(trials_per_case):
            conv = Conversation()
            agent = Agent(
                client=client,
                conversation=conv,
                registry=tool_reg,
                permission_manager=perm_mgr,
                router=router,
                settings=settings,
            )

            t0 = time.perf_counter()
            t_first: Optional[float] = None
            chunks = []

            for chunk in agent.stream_run(prompt, interactive=False):
                if t_first is None:
                    t_first = time.perf_counter()
                chunks.append(chunk)

            t_end = time.perf_counter()
            total_duration_ms = (t_end - t0) * 1000.0
            ttft_ms = ((t_first - t0) * 1000.0) if t_first else total_duration_ms

            ttft_samples.append(ttft_ms)
            total_samples.append(total_duration_ms)
            last_resp = "".join(chunks)

            # Detect tier
            if total_duration_ms < 20.0:
                tier_label = "DIRECT"
            else:
                tier_label = "FAST_LLM"

        med_ttft = statistics.median(ttft_samples) if ttft_samples else None
        p95_ttft = sorted(ttft_samples)[int(0.95 * len(ttft_samples))] if ttft_samples else None
        med_total = statistics.median(total_samples)
        p95_total = sorted(total_samples)[int(0.95 * len(total_samples))]

        res = BenchmarkResult(
            category=cat_name,
            prompt=prompt,
            trials=trials_per_case,
            median_ttft_ms=med_ttft,
            p95_ttft_ms=p95_ttft,
            median_total_ms=med_total,
            p95_total_ms=p95_total,
            tier=tier_label,
            sample_response=last_resp[:60],
        )
        results.append(res)

        ttft_str = f"{med_ttft:.2f} ms" if med_ttft else "N/A"
        p95_ttft_str = f"{p95_ttft:.2f} ms" if p95_ttft else "N/A"
        print(f"{cat_name:<32} | {tier_label:<8} | {ttft_str:<12} | {p95_ttft_str:<10} | {med_total:.2f} ms     | {p95_total:.2f} ms")

    return results


if __name__ == "__main__":
    run_benchmarks(trials_per_case=3)
