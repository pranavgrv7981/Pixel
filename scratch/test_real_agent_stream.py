import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.models.availability import ModelAvailabilityChecker
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry
from app.context import ContextManager

print("Initializing Real Agent components...")
settings = Settings(ollama_num_ctx=2048)
client = OllamaClient(settings=settings)
registry = ToolRegistry()
perm_mgr = PermissionManager(settings=settings)
model_reg = ModelRegistry(settings=settings)
avail = ModelAvailabilityChecker(client=client, settings=settings)
router = ModelRouter(registry=model_reg, availability_checker=avail, settings=settings)
ctx_mgr = ContextManager(settings=settings)
ctx_mgr.initialize()

conv = Conversation()
agent = Agent(
    client=client,
    conversation=conv,
    registry=registry,
    permission_manager=perm_mgr,
    router=router,
    context_manager=ctx_mgr,
    settings=settings,
)

print("\n--- TRACING ONE REAL STREAM_RUN FOR 'hi' ---")
t0 = time.perf_counter()
print(f"T0 (Request start): 0.00s")

first = True
chunks = []
for chunk in agent.stream_run("hi"):
    if first:
        t_first = time.perf_counter() - t0
        print(f"T8 (FIRST TOKEN): {t_first:.2f}s")
        first = False
    chunks.append(chunk)

t_final = time.perf_counter() - t0
print(f"T9 (FINAL TOKEN): {t_final:.2f}s")
full_resp = "".join(chunks)
print(f"T10 (Total response length): {len(full_resp)} chars")
print(f"Response preview: {full_resp[:120]}")
