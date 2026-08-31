import time
import sys
from pathlib import Path
import ollama

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

client = ollama.Client(host="http://localhost:11434")

print("Testing with num_ctx=4096...")
t0 = time.perf_counter()
first = True
full_chunks = []

try:
    stream = client.chat(
        model="qwen3:30b",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        options={"num_ctx": 4096},
    )
    for chunk in stream:
        token = chunk.get("message", {}).get("content", "")
        if token:
            if first:
                print(f"TTFT: {time.perf_counter() - t0:.2f}s")
                first = False
            full_chunks.append(token)

    print(f"\nTotal elapsed: {time.perf_counter() - t0:.2f}s")
    print(f"Full response length: {len(''.join(full_chunks))}")
    print(f"Response preview: {''.join(full_chunks)[:100]}")
except Exception as e:
    print(f"\nFailed with error: {e}")
