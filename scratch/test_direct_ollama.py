import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.ollama_client import OllamaClient

client = OllamaClient()
print("Ollama reachable:", client.check_connection())
print("Available models:", client.list_models())

t0 = time.perf_counter()
print("Starting stream request for 'hi' with qwen3:30b...")
first = True
full_chunks = []
for chunk in client.stream_chat([{"role": "user", "content": "hi"}], model="qwen3:30b"):
    if first:
        print(f"TTFT: {time.perf_counter() - t0:.2f}s")
        first = False
    full_chunks.append(chunk)

total_time = time.perf_counter() - t0
resp_text = "".join(full_chunks)
print(f"Total time: {total_time:.2f}s")
print(f"Response length: {len(resp_text)}")
print(f"Response preview: {resp_text[:120]}")
