"""Test methods to completely suppress thinking tokens in qwen3:4b for instant TTFT."""

import json
import time
import httpx


def test_request(name: str, payload_mods: dict):
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "qwen3:4b",
        "messages": [
            {"role": "user", "content": "Hello, who are you?"}
        ],
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "num_predict": 128,
            "temperature": 0.4,
        },
        "keep_alive": "30m",
    }
    payload.update(payload_mods)
    if "options" in payload_mods:
        payload["options"].update(payload_mods["options"])

    t_start = time.perf_counter()
    first_token_t = None
    first_vis_t = None
    all_tokens = []
    metadata = {}

    with httpx.Client(timeout=30.0) as client:
        with client.stream("POST", url, json=payload) as response:
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                now = time.perf_counter()
                if first_token_t is None:
                    first_token_t = now

                content = data.get("message", {}).get("content", "")
                if content:
                    all_tokens.append(content)
                    if first_vis_t is None and not content.startswith("<think>"):
                        first_vis_t = now

                if data.get("done", False):
                    metadata = data

    t_end = time.perf_counter()
    total_ms = (t_end - t_start) * 1000.0
    ttft_raw_ms = ((first_token_t - t_start) * 1000.0) if first_token_t else total_ms
    ttft_vis_ms = ((first_vis_t - t_start) * 1000.0) if first_vis_t else total_ms

    full_output = "".join(all_tokens)
    has_think = "<think>" in full_output or "think" in full_output[:30].lower()

    print(f"\n--- Strategy: {name} ---")
    print(f"Total: {total_ms:.1f}ms | TTFT_raw: {ttft_raw_ms:.1f}ms | TTFT_vis: {ttft_vis_ms:.1f}ms | Tokens: {len(all_tokens)}")
    print(f"Contains <think>: {has_think}")
    preview = full_output.replace("\n", " ")[:120].encode('ascii', errors='replace').decode('ascii')
    print(f"Output: {preview}")


if __name__ == "__main__":
    # Baseline
    test_request("1. Baseline (no system prompt)", {})

    # Strategy 2: System prompt enforcing no thinking
    test_request("2. System prompt: direct answer", {
        "messages": [
            {"role": "system", "content": "You are Pixel, a helpful desktop AI assistant. Answer directly and concisely. Do not deliberate or think aloud."},
            {"role": "user", "content": "Hello, who are you?"}
        ]
    })

    # Strategy 3: System prompt with /no_think directive
    test_request("3. System prompt: /no_think", {
        "messages": [
            {"role": "system", "content": "You are Pixel. /no_think Answer directly in one sentence."},
            {"role": "user", "content": "Hello, who are you?"}
        ]
    })

    # Strategy 4: Direct prompt prefixing
    test_request("4. Prompt prefix: [Direct Answer]", {
        "messages": [
            {"role": "system", "content": "You are Pixel, an instant desktop assistant. Output ONLY the direct final response."},
            {"role": "user", "content": "Hello, who are you? Answer directly without thinking."}
        ]
    })

    # Strategy 5: Stop parameter
    test_request("5. System prompt + temperature 0.2", {
        "messages": [
            {"role": "system", "content": "You are Pixel, a fast desktop assistant. Answer immediately without thinking tags."},
            {"role": "user", "content": "Hello, who are you?"}
        ],
        "options": {
            "temperature": 0.2,
        }
    })
