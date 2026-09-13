"""Test bypassing hardcoded <think> prefix in qwen3:4b template."""

import json
import time
import httpx


def test_payload(name: str, messages: list, options: dict = None):
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "qwen3:4b",
        "messages": messages,
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "num_predict": 128,
            "temperature": 0.4,
        },
        "keep_alive": "30m",
    }
    if options:
        payload["options"].update(options)

    t0 = time.perf_counter()
    first_tok_t = None
    chunks = []

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

    t1 = time.perf_counter()
    raw_ttft = ((first_tok_t - t0) * 1000.0) if first_tok_t else (t1 - t0) * 1000.0
    total_ms = (t1 - t0) * 1000.0
    text = "".join(chunks)

    print(f"\n[{name}]")
    print(f"Total: {total_ms:.1f}ms | TTFT: {raw_ttft:.1f}ms | Chunks: {len(chunks)}")
    preview = text.replace('\n', ' ')[:100].encode('ascii', errors='replace').decode('ascii')
    print(f"Content: {preview}")


if __name__ == "__main__":
    test_payload("1. Standard User Message", [
        {"role": "user", "content": "Hello, who are you?"}
    ])

    test_payload("2. User with empty Assistant priming", [
        {"role": "user", "content": "Hello, who are you?"},
        {"role": "assistant", "content": ""}
    ])

    test_payload("3. User with closed think tag in Assistant priming", [
        {"role": "user", "content": "Hello, who are you?"},
        {"role": "assistant", "content": "</think>"}
    ])

    test_payload("4. System with empty think block instruction", [
        {"role": "system", "content": "You are Pixel. Reply concisely."},
        {"role": "user", "content": "Hello, who are you?"},
        {"role": "assistant", "content": "</think>Hello! I am Pixel,"}
    ])

    test_payload("5. Stop sequence on think", [
        {"role": "user", "content": "Hello, who are you?"},
        {"role": "assistant", "content": "</think>"}
    ], options={"stop": ["<think>"]})
