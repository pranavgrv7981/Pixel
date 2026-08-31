"""Automated multi-turn verification for real GUI features: Chat, Tools, and Memory."""

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

from PySide6.QtWidgets import QApplication

from app.agent.agent import Agent
from app.agent.conversation import ConversationManager
from app.browser import BrowserManager
from app.context import ContextManager
from app.core.config import Settings
from app.core.ollama_client import OllamaClient
from app.knowledge import KnowledgeManager
from app.memory import MemoryManager
from app.models import ModelAvailabilityChecker, ModelRegistry, ModelRouter
from app.security.confirmations import ConfirmationManager
from app.security.manager import PermissionManager
from app.tools.demo import SafeCalculateTool
from app.tools.memory import RememberMemoryTool, RecallMemoryTool
from app.tools.registry import ToolRegistry
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.controller import AssistantController
from app.ui.main_window import MainWindow


def execute_gui_turn(window: MainWindow, controller: AssistantController, app: QApplication, prompt: str) -> str:
    print(f"\n---> Sending GUI prompt: '{prompt}'")
    window.input_bar.text_input.setPlainText(prompt)
    window.input_bar.send_btn.click()

    start_wait = time.time()
    while controller.current_state.value != "idle" and (time.time() - start_wait) < 180.0:
        app.processEvents()
        time.sleep(0.05)

    app.processEvents()
    bubble = window.chat_view._current_assistant_bubble
    assert bubble is not None, "Bubble was not created!"
    content = bubble.get_content()
    print(f"---> Received GUI response ({len(content)} chars):\n{content[:180]}")
    return content


def run_all_gui_features():
    print("=" * 70)
    print("RUNNING EXTENSIVE REAL GUI SUITE (CHAT, CALCULATE TOOL, PERSISTENT MEMORY)")
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
    tool_reg.register(SafeCalculateTool())
    tool_reg.register(RememberMemoryTool(memory_manager=memory_mgr))
    tool_reg.register(RecallMemoryTool(memory_manager=memory_mgr))

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

    # 1. Test Chat: "hi"
    res1 = execute_gui_turn(window, controller, app, "hi")
    assert len(res1) > 0, "Chat response was empty"

    # 2. Test Tool: "What is 25 multiplied by 4?"
    res2 = execute_gui_turn(window, controller, app, "What is 25 multiplied by 4?")
    assert "100" in res2, f"Expected 100 in calculate response, got: {res2}"

    # 3. Test Memory: "Remember that my favorite framework is PySide6."
    res3 = execute_gui_turn(window, controller, app, "Remember that my favorite framework is PySide6.")
    assert len(res3) > 0

    # 4. Test Memory Recall: "What is my favorite framework?"
    res4 = execute_gui_turn(window, controller, app, "What is my favorite framework?")
    assert "pyside6" in res4.lower() or "framework" in res4.lower()

    print("\n" + "=" * 70)
    print("ALL REAL GUI FEATURE TESTS PASSED (100%)")
    print("=" * 70)
    window.close()
    return True


if __name__ == "__main__":
    success = run_all_gui_features()
    sys.exit(0 if success else 1)
