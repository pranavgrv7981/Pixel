"""End-to-end automated verification of the REAL GUI chat path with real qwen3:30b."""

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.agent.agent import Agent
from app.agent.conversation import ConversationManager
from app.browser import BrowserManager
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.knowledge import KnowledgeManager
from app.memory import MemoryManager
from app.models import ModelAvailabilityChecker, ModelRegistry, ModelRouter
from app.security.confirmations import ConfirmationManager
from app.security.manager import PermissionManager
from app.tools.registry import ToolRegistry
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.controller import AssistantController
from app.ui.main_window import MainWindow
from app.context import ContextManager


def run_gui_chat_test():
    print("=" * 70)
    print("TESTING REAL GUI CHAT PIPELINE (GUI -> Worker -> Agent -> Ollama -> GUI)")
    print("=" * 70)

    app = QApplication.instance() or QApplication(sys.argv)

    settings = Settings(ollama_num_ctx=2048)
    client = OllamaClient(settings=settings)
    memory_mgr = MemoryManager(settings=settings)
    memory_mgr.initialize()
    knowledge_mgr = KnowledgeManager(settings=settings)
    knowledge_mgr.initialize()
    browser_mgr = BrowserManager(settings=settings)

    conv_mgr = ConversationManager(client=client, settings=settings, memory_manager=memory_mgr)

    perm_mgr = PermissionManager(settings=settings)
    tool_reg = ToolRegistry()
    model_reg = ModelRegistry(settings=settings)
    avail = ModelAvailabilityChecker(client=client, settings=settings)
    router = ModelRouter(registry=model_reg, availability_checker=avail, settings=settings)
    ctx_mgr = ContextManager(memory_manager=memory_mgr, knowledge_manager=knowledge_mgr, settings=settings)
    ctx_mgr.initialize()

    agent = Agent(
        client=client,
        conversation=conv_mgr.active_conversation,
        registry=tool_reg,
        permission_manager=perm_mgr,
        memory_manager=memory_mgr,
        router=router,
        context_manager=ctx_mgr,
        settings=settings,
    )

    gui_conf = GuiConfirmationProvider()
    controller = AssistantController(
        agent=agent,
        conversation_manager=conv_mgr,
        memory_manager=memory_mgr,
        knowledge_manager=knowledge_mgr,
        browser_manager=browser_mgr,
        permission_manager=perm_mgr,
        gui_confirmation=gui_conf,
        context_manager=ctx_mgr,
        settings=settings,
    )

    window = MainWindow(controller=controller)
    window.show()

    print("[Step 1] GUI Window created and shown.")
    print(f"[Step 2] Setting input bar text to 'hi'...")
    window.input_bar.text_input.setPlainText("hi")

    t0 = time.perf_counter()
    first_chunk_time = None
    chunks_received = []

    def on_chunk(chunk: str):
        nonlocal first_chunk_time
        if first_chunk_time is None:
            first_chunk_time = time.perf_counter() - t0
            print(f"  -> FIRST CHUNK RECEIVED BY GUI at {first_chunk_time:.2f}s: '{chunk.strip()}'")
        chunks_received.append(chunk)

    controller.chunk_received.connect(on_chunk)

    print("[Step 3] Clicking Send button...")
    window.input_bar.send_btn.click()

    print("[Step 4] Processing Qt event loop while waiting for real qwen3:30b response...")
    # Poll event loop until turn completed or timeout (180s)
    max_wait = 180.0
    start_wait = time.time()
    while controller.current_state.value != "idle" and (time.time() - start_wait) < max_wait:
        app.processEvents()
        time.sleep(0.05)

    app.processEvents()

    total_time = time.perf_counter() - t0
    print(f"[Step 5] Turn completed in {total_time:.2f}s.")
    print(f"  -> Total chunks received by GUI: {len(chunks_received)}")

    # Inspect the rendered assistant bubble
    bubble = window.chat_view._current_assistant_bubble
    assert bubble is not None, "Assistant message bubble was not created!"
    rendered_text = bubble.get_content()
    print(f"  -> Final Rendered Bubble Content ({len(rendered_text)} chars):")
    print(f"     \"{rendered_text[:140]}...\"")

    assert len(rendered_text) > 0, "Rendered assistant bubble is empty!"
    assert not bubble._is_thinking, "Assistant bubble is still stuck in Thinking state!"
    assert "Unable to generate a response" not in rendered_text, f"Assistant returned an error: {rendered_text}"

    print("\n" + "=" * 70)
    print("REAL GUI CHAT VERIFICATION PASSED (100%)")
    print("=" * 70)
    window.close()
    return True


if __name__ == "__main__":
    success = run_gui_chat_test()
    sys.exit(0 if success else 1)
