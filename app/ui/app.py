"""Desktop application startup routine, system tray residency, and lifecycle bootstrapping."""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys
from typing import Optional
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from app.agent.agent import Agent
from app.agent.conversation import ConversationManager
from app.browser import BrowserManager
from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging
from app.core.ollama_client import OllamaClient
from app.core.ollama_manager import OllamaManager
from app.core.single_instance import SingleInstanceManager
from app.core.startup import WindowsStartupManager
from app.events import EventDatabase, EventEngine, EventRepository
from app.knowledge import KnowledgeManager
from app.memory import MemoryManager
from app.security.confirmations import ConfirmationManager
from app.security.manager import PermissionManager
from app.tasks import TaskDatabase, TaskManager, TaskRepository
from app.ui.automation_controller import AutomationController
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.controller import AssistantController
from app.ui.main_window import MainWindow
from app.ui.task_controller import TaskController
from app.ui.tray import AssistantTrayIcon

logger = get_logger("ui.app")


def run_gui(
    settings: Optional[Settings] = None,
    model: Optional[str] = None,
    background_mode: bool = False,
) -> int:
    """Initialize all backend subsystems and launch the PySide6 desktop GUI / tray assistant."""
    cfg = settings or get_settings()
    setup_logging(cfg)
    logger.info("Initializing Desktop Application (v%s, background_mode=%s)...", cfg.version, background_mode)

    # ── 1. SINGLE INSTANCE CHECK (must be first — before ANY backend init) ──
    # check_is_secondary() does only a lightweight port probe + WAKEUP/ACK.
    # Secondary instances exit here without touching memory, DB, tools, or Qt.
    single_instance = SingleInstanceManager(settings=cfg)
    if single_instance.check_is_secondary():
        logger.info("Existing assistant instance is already active. Waking up instance and exiting.")
        return 0

    # ── 1b. PRIMARY LOCK ACQUISITION ──
    # Now that we know no healthy primary exists, acquire the lock.
    # This binds the port, writes the PID file, and starts the listener thread.
    if not single_instance.acquire():
        # Race condition: another instance started between check and acquire
        logger.info("Instance lock taken by concurrent launch. Exiting.")
        return 0

    # 2. Ollama Lifecycle Manager
    ollama_manager = OllamaManager(settings=cfg)
    if cfg.auto_start_ollama and not ollama_manager.is_server_running():
        logger.info("Ollama is not running. Attempting automated background start...")
        started = ollama_manager.start_server(wait_seconds=30.0)
        if not started:
            logger.warning("Could not auto-start Ollama. Assistant will start in degraded mode.")

    if cfg.preload_model and ollama_manager.is_server_running():
        ollama_manager.preload_model_if_requested(model or cfg.default_model)

    # 3. Initialize Qt Application
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName(cfg.app_name)
    app.setQuitOnLastWindowClosed(False)  # Allow resident system tray operation

    # 4. Ollama Client
    client = OllamaClient(
        base_url=cfg.ollama_base_url,
        timeout=cfg.ollama_timeout_seconds,
        default_model=model or cfg.default_model,
        settings=cfg,
    )

    # 5. Persistence and Knowledge Subsystems
    memory_manager = MemoryManager(settings=cfg)
    memory_manager.initialize()

    knowledge_manager = KnowledgeManager(settings=cfg)
    knowledge_manager.initialize()

    browser_manager = BrowserManager(settings=cfg)

    conversation_manager = ConversationManager(
        client=client,
        settings=cfg,
        memory_manager=memory_manager,
    )

    # 6. Tasks & Event Subsystems (Phase 14)
    task_db = TaskDatabase(settings=cfg)
    task_repo = TaskRepository(db=task_db)
    task_manager = TaskManager(repository=task_repo, settings=cfg)

    event_db = EventDatabase(settings=cfg)
    event_repo = EventRepository(db=event_db)
    event_engine = EventEngine(repository=event_repo, settings=cfg)

    # 7. Tool Registry (65 tools registered)
    from main import get_default_tool_registry

    registry = get_default_tool_registry(
        settings=cfg,
        memory_manager=memory_manager,
        knowledge_manager=knowledge_manager,
        browser_manager=browser_manager,
        task_manager=task_manager,
        event_engine=event_engine,
    )

    # 8. GUI Confirmation & Permission Security
    gui_confirmation = GuiConfirmationProvider()
    confirmation_manager = ConfirmationManager(provider=gui_confirmation)
    permission_manager = PermissionManager(
        settings=cfg,
        confirmation_manager=confirmation_manager,
    )

    # 9. Model Routing & Agent Orchestrator (Phase 16)
    from app.models import (
        ModelAvailabilityChecker,
        ModelMetricsTracker,
        ModelRegistry,
        ModelResourceManager,
        ModelRouter,
        ModelSelector,
    )

    model_registry = ModelRegistry(settings=cfg)
    model_avail_checker = ModelAvailabilityChecker(client=client, settings=cfg)
    model_selector = ModelSelector(settings=cfg)
    model_router = ModelRouter(
        registry=model_registry,
        availability_checker=model_avail_checker,
        selector=model_selector,
        settings=cfg,
    )
    model_metrics = ModelMetricsTracker()
    model_resource_mgr = ModelResourceManager(client=client, settings=cfg)

    # 9b. Context Management Layer (Phase 17)
    from app.context import ContextManager
    context_manager = ContextManager(
        memory_manager=memory_manager,
        knowledge_manager=knowledge_manager,
        settings=cfg,
    )
    context_manager.initialize()

    agent = Agent(
        conversation=conversation_manager.active_conversation,
        client=client,
        registry=registry,
        permission_manager=permission_manager,
        memory_manager=memory_manager,
        router=model_router,
        context_manager=context_manager,
        metrics_tracker=model_metrics,
        max_rounds=cfg.max_tool_call_rounds,
        settings=cfg,
    )


    # Connect non-interactive agent execution to task manager and event engine
    def _execute_agent_action(prompt: str, interactive: bool = False) -> str:
        result = agent.run(prompt, interactive=interactive)
        return result if isinstance(result, str) else str(result)

    task_manager.agent_executor = _execute_agent_action
    event_engine.agent_executor = _execute_agent_action

    # 10. Voice Subsystems (STT & TTS)
    from app.voice.manager import VoiceManager
    from app.voice.tts_manager import TTSManager
    from app.ui.voice_controller import VoiceController
    from app.ui.tts_controller import TTSController

    voice_manager = VoiceManager(settings=cfg)
    voice_controller = VoiceController(voice_manager=voice_manager, settings=cfg)

    tts_manager = TTSManager(settings=cfg)
    tts_controller = TTSController(tts_manager=tts_manager, settings=cfg)

    # 11. Controllers
    task_controller = TaskController(task_manager=task_manager, settings=cfg)
    automation_controller = AutomationController(
        event_engine=event_engine,
        task_manager=task_manager,
        settings=cfg,
    )

    controller = AssistantController(
        agent=agent,
        conversation_manager=conversation_manager,
        memory_manager=memory_manager,
        knowledge_manager=knowledge_manager,
        browser_manager=browser_manager,
        permission_manager=permission_manager,
        gui_confirmation=gui_confirmation,
        voice_manager=voice_manager,
        tts_manager=tts_manager,
        task_manager=task_manager,
        event_engine=event_engine,
        context_manager=context_manager,
        settings=cfg,
    )

    # 12. Main Window
    window = MainWindow(
        controller=controller,
        voice_controller=voice_controller,
        tts_controller=tts_controller,
        task_controller=task_controller,
        automation_controller=automation_controller,
    )

    # Connect thread-safe single-instance activation callback
    class InstanceWakeupBridge(QObject):
        woke = Signal()

    wakeup_bridge = InstanceWakeupBridge()

    def _restore_window_on_wakeup() -> None:
        logger.info("Instance wakeup received: restoring and raising Pixel MainWindow to foreground.")
        window.summon_pixel("single_instance")

    wakeup_bridge.woke.connect(_restore_window_on_wakeup)

    def _on_secondary_instance_woke() -> None:
        logger.info("Secondary instance notified primary on listener thread; signaling main GUI thread.")
        wakeup_bridge.woke.emit()

    single_instance.on_activate = _on_secondary_instance_woke

    # 13. Global Hotkey Manager (Alt + P Summoning)
    from app.ui.hotkey import GlobalHotkeyManager
    hotkey_manager = GlobalHotkeyManager(
        hotkey_str=cfg.global_hotkey,
        on_trigger=lambda: window.summon_pixel("hotkey"),
    )
    hotkey_manager.start()

    # 14. Voice Wake Detector ("Pixel, open")
    from app.voice.wake import VoiceWakeDetector
    voice_wake_detector = VoiceWakeDetector(
        settings=cfg,
        stt_provider=voice_manager.provider,
        on_wake=lambda phrase: window.summon_pixel("voice"),
    )
    if cfg.voice_wake_enabled:
        voice_wake_detector.start()

    # 15. System Tray Resident Icon
    tray_icon = AssistantTrayIcon(
        main_window=window,
        automation_toggle_callback=automation_controller.set_automation_enabled,
        open_automation_callback=window._open_automation,
        voice_wake_toggle_callback=voice_wake_detector.set_enabled,
        new_chat_callback=controller.new_conversation,
        open_settings_callback=window._open_settings,
    )
    tray_icon.set_voice_wake_checked(cfg.voice_wake_enabled)
    tray_icon.show()

    # Route notifications to Tray and TTS (if configured)
    def _on_notification_received(title: str, message: str, severity: str) -> None:
        tray_icon.show_notification(title, message, severity=severity)
        if cfg.speak_background_notifications and tts_controller:
            tts_controller.speak_text(f"{title}. {message}", interrupt_current=False)

    automation_controller.event_notification.connect(_on_notification_received)
    task_controller.task_notification.connect(
        lambda title, result, success: _on_notification_received(
            title,
            result,
            "info" if success else "warning",
        )
    )

    # Start Event Engine
    if cfg.automation_enabled:
        event_engine.start()

    # Handle application shutdown cleanup
    def _cleanup_on_quit() -> None:
        logger.info("Application shutting down...")
        try:
            hotkey_manager.stop()
            voice_wake_detector.stop()
            event_engine.stop()
            task_manager.shutdown()
            single_instance.release()
            ollama_manager.stop_if_owned()
        except Exception as err:
            logger.warning("Error during application shutdown: %s", err)

    app.aboutToQuit.connect(_cleanup_on_quit)

    # Display or background residency
    should_start_bg = background_mode or cfg.start_in_background
    if not should_start_bg:
        window.summon_pixel("startup")
        logger.info(
            "Desktop GUI window displayed (visible=%s, minimized=%s, geometry=%s).",
            window.isVisible(),
            window.isMinimized(),
            window.geometry().getRect(),
        )
    else:
        logger.info("Pixel started in background resident mode (system tray & global hotkey active).")
        tray_icon.show_notification("Pixel Resident", "Pixel is active in background (Alt+P to summon).", severity="info")

    return app.exec()
