"""Test prefilling </think> in assistant message for qwen3:4b."""

import json
import time
import httpx


def test_prefilled_think(prompt: str):
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "qwen3:4b",
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "</think>"}
        ],
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "num_predict": 128,
            "temperature": 0.3,
        },
        "keep_alive": "30m",
    }

    t0 = time.perf_counter()
    first_tok_t = None
    chunks = []
    meta = {}

    with httpx.Client(timeout=30.0) as client:
        with client.stream("POST", url, json=payload) as resp:
            for line in resp.iter_lines():
                if not line:
                    continue
                d = json.loads(line)
                now = time.perf_counter()
                if first_tok_t is None:
                    first_tok_t = now
                c = d.get("message", {}).get("content", "")
                if c:
                    chunks.append(c)
                if d.get("done", False):
                    meta = d

    t1 = time.perf_counter()
    raw_ttft = ((first_tok_t - t0) * 1000.0) if first_tok_t else (t1 - t0) * 1000.0
    total_ms = (t1 - t0) * 1000.0
    text = "".join(chunks)

    load_ms = meta.get("load_duration", 0) / 1e6
    prompt_eval_ms = meta.get("prompt_eval_duration", 0) / 1e6
    prompt_eval_count = meta.get("prompt_eval_count", 0)
    eval_ms = meta.get("eval_duration", 0) / 1e6
    eval_count = meta.get("eval_count", 0)

    print(f"\nPrompt: '{prompt}'")
    print(f"Total: {total_ms:.1f}ms | TTFT: {raw_ttft:.1f}ms | Load: {load_ms:.1f}ms | PromptEval: {prompt_eval_ms:.1f}ms ({prompt_eval_count} tok) | Eval: {eval_ms:.1f}ms ({eval_count} tok)")
    preview = text.replace('\n', ' ')[:100].encode('ascii', errors='replace').decode('ascii')
    print(f"Output: {preview}")


if __name__ == "__main__":
    for i in range(3):
        print(f"--- Iteration {i+1} ---")
        test_prefilled_think("Hello, who are you?")
        test_prefilled_think("Explain the difference between synchronous and asynchronous code in 2 sentences")
