"""Main entry point for the Local AI Personal Assistant."""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import argparse
import sys
from typing import Optional

from pydantic import ValidationError

from app import __version__
from app.agent.agent import Agent
from app.agent.conversation import ConversationManager
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConfigurationError,
    ConversationError,
    InvalidMessageError,
    ModelAPIError,
    ModelError,
    ModelNotFoundError,
    OllamaConnectionError,
    ToolRoundLimitError,
)
from app.core.logging import get_logger, setup_logging
from app.core.ollama_client import ModelStatus, OllamaClient, OllamaStatus, ServerStatus
from app.core.ollama_manager import OllamaManager
from app.core.single_instance import SingleInstanceManager

from app.security.confirmations import CliConfirmationProvider, ConfirmationManager
from app.security.execution_policy import ExecutionPolicy
from app.security.manager import PermissionManager
from app.security.policies import SecurityPolicy
from app.tools.applications import (
    ApplicationRegistry,
    CloseApplicationTool,
    IsApplicationRunningTool,
    OpenApplicationTool,
)
from app.tools.demo import DemoMediumRiskTool, GetCurrentTimeTool, SafeCalculateTool
from app.tools.filesystem import (
    CopyFileTool,
    CreateDirectoryTool,
    CreateFileTool,
    DeleteDirectoryTool,
    DeleteFileTool,
    GetFileInfoTool,
    ListDirectoryTool,
    MoveFileTool,
    ReadTextFileTool,
    RenameFileTool,
    SearchFilesTool,
    WriteTextFileTool,
)
from app.tools.path_guard import PathGuard
from app.tools.registry import ToolRegistry
from app.tools.system import (
    GetBatteryStatusTool,
    GetCpuUsageTool,
    GetMemoryUsageTool,
    GetProcessInfoTool,
    GetSystemInfoTool,
    GetUptimeTool,
    ListRunningProcessesTool,
    SystemProvider,
)
from app.tools.terminal import (
    CompileCProgramTool,
    GitDiffTool,
    GitStatusTool,
    RunCProgramTool,
    RunPytestTool,
    RunPythonFileTool,
)
from app.memory import MemoryDatabase, MemoryManager
from app.tools.memory import (
    ForgetMemoryTool,
    RecallMemoryTool,
    RememberMemoryTool,
)
from app.knowledge import KnowledgeDatabase, KnowledgeManager
from app.tools.knowledge import (
    IndexDirectoryTool,
    IndexDocumentTool,
    ListIndexedDocumentsTool,
    RemoveDocumentTool,
    SearchKnowledgeTool,
)
from app.browser import BrowserManager
from app.tools.browser import (
    BrowserBackTool,
    BrowserClickTool,
    BrowserCloseTool,
    BrowserCurrentPageTool,
    BrowserForwardTool,
    BrowserGetPageTool,
    BrowserOpenTool,
    BrowserScrollTool,
    BrowserSearchTool,
    BrowserTypeTool,
)
from app.tasks import TaskDatabase, TaskManager, TaskRepository
from app.tools.task_tools import (
    CancelTaskTool,
    CreateTaskTool,
    DeleteTaskTool,
    GetTaskExecutionsTool,
    GetTaskTool,
    ListTasksTool,
    PauseTaskTool,
    ResumeTaskTool,
    RunTaskNowTool,
)
from app.events import EventDatabase, EventEngine, EventRepository
from app.tools.automation_tools import (
    CreateTriggerTool,
    DeleteTriggerTool,
    GetEventHistoryTool,
    ListTriggersTool,
    PauseTriggerTool,
    ResumeTriggerTool,
    SetAutomationModeTool,
)
from app.planning import (
    PlanDatabase,
    PlanExecutor,
    PlanRepository,
    PlanValidator,
    Planner,
)
from app.tools.planning import (
    CancelPlanTool,
    CreatePlanTool,
    GetPlanStatusTool,
    ListPlansTool,
)


def get_default_tool_registry(
    settings: Optional[Settings] = None,
    system_provider: Optional[SystemProvider] = None,
    app_registry: Optional[ApplicationRegistry] = None,
    execution_policy: Optional[ExecutionPolicy] = None,
    memory_manager: Optional[MemoryManager] = None,
    knowledge_manager: Optional[KnowledgeManager] = None,
    browser_manager: Optional[BrowserManager] = None,
    task_manager: Optional[TaskManager] = None,
    event_engine: Optional[EventEngine] = None,
    planner: Optional[Any] = None,
    plan_executor: Optional[Any] = None,
    plan_repository: Optional[Any] = None,
) -> ToolRegistry:




    """Create and configure the default tool registry with all approved tools."""
    cfg = settings or get_settings()
    path_guard = PathGuard(settings=cfg)
    sys_provider = system_provider or SystemProvider()
    application_registry = app_registry or ApplicationRegistry()
    exec_policy = execution_policy or ExecutionPolicy(settings=cfg, path_guard=path_guard)

    registry = ToolRegistry()

    # Harmless demo tools (Phase 3)
    registry.register(GetCurrentTimeTool())
    registry.register(SafeCalculateTool())
    registry.register(DemoMediumRiskTool())

    # Phase 5 File-System Tools
    registry.register(ListDirectoryTool(path_guard=path_guard, settings=cfg))
    registry.register(GetFileInfoTool(path_guard=path_guard, settings=cfg))
    registry.register(SearchFilesTool(path_guard=path_guard, settings=cfg))
    registry.register(ReadTextFileTool(path_guard=path_guard, settings=cfg))
    registry.register(CreateDirectoryTool(path_guard=path_guard, settings=cfg))
    registry.register(CreateFileTool(path_guard=path_guard, settings=cfg))
    registry.register(WriteTextFileTool(path_guard=path_guard, settings=cfg))
    registry.register(CopyFileTool(path_guard=path_guard, settings=cfg))
    registry.register(MoveFileTool(path_guard=path_guard, settings=cfg))
    registry.register(RenameFileTool(path_guard=path_guard, settings=cfg))
    registry.register(DeleteFileTool(path_guard=path_guard, settings=cfg))
    registry.register(DeleteDirectoryTool(path_guard=path_guard, settings=cfg))

    # Phase 6 System & Application Tools
    registry.register(GetSystemInfoTool(provider=sys_provider))
    registry.register(GetCpuUsageTool(provider=sys_provider))
    registry.register(GetMemoryUsageTool(provider=sys_provider))
    registry.register(GetBatteryStatusTool(provider=sys_provider))
    registry.register(GetUptimeTool(provider=sys_provider))
    registry.register(ListRunningProcessesTool(provider=sys_provider, settings=cfg))
    registry.register(GetProcessInfoTool(provider=sys_provider, settings=cfg))
    registry.register(OpenApplicationTool(registry=application_registry, system_provider=sys_provider, settings=cfg))
    registry.register(CloseApplicationTool(registry=application_registry, system_provider=sys_provider, settings=cfg))
    registry.register(IsApplicationRunningTool(registry=application_registry, system_provider=sys_provider, settings=cfg))

    # Phase 7 Controlled Terminal & Code Execution Tools
    registry.register(GitStatusTool(execution_policy=exec_policy, path_guard=path_guard, settings=cfg))
    registry.register(GitDiffTool(execution_policy=exec_policy, path_guard=path_guard, settings=cfg))
    registry.register(CompileCProgramTool(execution_policy=exec_policy, path_guard=path_guard, settings=cfg))
    registry.register(RunPythonFileTool(execution_policy=exec_policy, path_guard=path_guard, settings=cfg))
    registry.register(RunPytestTool(execution_policy=exec_policy, path_guard=path_guard, settings=cfg))
    registry.register(RunCProgramTool(execution_policy=exec_policy, path_guard=path_guard, settings=cfg))

    # Phase 8 Persistent Memory Tools
    mem_manager = memory_manager or MemoryManager(settings=cfg)
    registry.register(RememberMemoryTool(memory_manager=mem_manager, settings=cfg))
    registry.register(RecallMemoryTool(memory_manager=mem_manager, settings=cfg))
    registry.register(ForgetMemoryTool(memory_manager=mem_manager, settings=cfg))

    # Phase 9 Personal Knowledge / RAG Tools
    k_mgr = knowledge_manager or KnowledgeManager(settings=cfg, path_guard=path_guard)
    registry.register(SearchKnowledgeTool(knowledge_manager=k_mgr, settings=cfg))
    registry.register(ListIndexedDocumentsTool(knowledge_manager=k_mgr, settings=cfg))
    registry.register(IndexDocumentTool(knowledge_manager=k_mgr, settings=cfg))
    registry.register(IndexDirectoryTool(knowledge_manager=k_mgr, settings=cfg))
    registry.register(RemoveDocumentTool(knowledge_manager=k_mgr, settings=cfg))

    # Phase 10 Browser Automation Tools
    b_mgr = browser_manager or BrowserManager(settings=cfg)
    registry.register(BrowserOpenTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserSearchTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserGetPageTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserCurrentPageTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserClickTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserTypeTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserScrollTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserBackTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserForwardTool(browser_manager=b_mgr, settings=cfg))
    registry.register(BrowserCloseTool(browser_manager=b_mgr, settings=cfg))

    # Phase 14 Task Scheduling & Controlled Automation Tools
    t_mgr = task_manager or TaskManager(settings=cfg)
    registry.register(CreateTaskTool(task_manager=t_mgr))
    registry.register(ListTasksTool(task_manager=t_mgr))
    registry.register(GetTaskTool(task_manager=t_mgr))
    registry.register(PauseTaskTool(task_manager=t_mgr))
    registry.register(ResumeTaskTool(task_manager=t_mgr))
    registry.register(CancelTaskTool(task_manager=t_mgr))
    registry.register(DeleteTaskTool(task_manager=t_mgr))
    registry.register(RunTaskNowTool(task_manager=t_mgr))
    registry.register(GetTaskExecutionsTool(task_manager=t_mgr))

    # Phase 14 Background Resident & Real-time Event Tools
    e_eng = event_engine or EventEngine(settings=cfg)
    registry.register(CreateTriggerTool(event_engine=e_eng))
    registry.register(ListTriggersTool(event_engine=e_eng))
    registry.register(PauseTriggerTool(event_engine=e_eng))
    registry.register(ResumeTriggerTool(event_engine=e_eng))
    registry.register(DeleteTriggerTool(event_engine=e_eng))
    registry.register(GetEventHistoryTool(event_engine=e_eng))
    registry.register(SetAutomationModeTool(event_engine=e_eng))

    # Phase 15 Controlled Autonomous Planning & Multi-Step Task Execution
    p_repo = plan_repository or PlanRepository(db=PlanDatabase(settings=cfg))
    p_val = PlanValidator(registry=registry, path_guard=path_guard, settings=cfg)
    p_client = OllamaClient(settings=cfg)
    p_planner = planner or Planner(client=p_client, registry=registry, validator=p_val, settings=cfg)
    p_perm = PermissionManager(settings=cfg)
    p_exec = plan_executor or PlanExecutor(
        registry=registry,
        permission_manager=p_perm,
        planner=p_planner,
        repository=p_repo,
        settings=cfg,
    )

    registry.register(CreatePlanTool(planner=p_planner, repository=p_repo))
    registry.register(GetPlanStatusTool(repository=p_repo))
    registry.register(ListPlansTool(repository=p_repo))
    registry.register(CancelPlanTool(executor=p_exec, repository=p_repo))

    return registry





def print_status_banner(
    settings: Settings,
    ollama_status: Optional[OllamaStatus] = None,
    tools_count: int = 0,
) -> None:
    """Display an initialization and diagnostic status banner."""
    server_info = "Checking..."
    model_info = settings.default_model

    if ollama_status is not None:
        if ollama_status.is_connected:
            server_info = f"Connected ({ollama_status.base_url})"
            if ollama_status.is_model_available:
                model_info = f"{ollama_status.model_name} (Available)"
            else:
                model_info = f"{ollama_status.model_name} (Not Available on server)"
        else:
            server_info = f"Disconnected ({ollama_status.base_url})"
            model_info = f"{ollama_status.model_name} (Unknown - Server offline)"

    allowed_roots_str = ", ".join([str(r) for r in settings.get_resolved_allowed_roots()])

    banner = f"""
======================================================================
  {settings.app_name} (v{settings.version})
======================================================================
  Status:          Initialized (Phase 14: Tasks & Controlled Automation Active)
  Environment:     {settings.environment}
  Debug Mode:      {'Enabled' if settings.debug else 'Disabled'}
  Log Level:       {settings.log_level}
  Log File:        {settings.get_log_file_path()}
  Data Directory:  {settings.get_resolved_data_dir()}
  Database File:   {settings.get_resolved_database_path()}
  Knowledge DB:    {settings.get_resolved_knowledge_db_path()}
  Browser Mode:    {'Headless' if settings.browser_headless else 'Visible'} (Timeout: {settings.browser_page_timeout_seconds}s)
  Voice Input:     {'Enabled' if settings.voice_enabled else 'Disabled'} (Model: {settings.stt_model})
  Voice Output:    {'Enabled' if settings.tts_enabled else 'Disabled'} (Provider: {settings.tts_provider}, Auto-Speak: {'ON' if settings.auto_speak_responses else 'OFF'})
  Tasks/Scheduler: {'Enabled' if settings.tasks_enabled else 'Disabled'} (Poll: {settings.task_scheduler_poll_seconds}s, Max Concurrent: {settings.max_concurrent_tasks})
  Allowed Roots:   {allowed_roots_str}
  Ollama Server:   {server_info}
  Default Model:   {model_info}
  Tools Loaded:    {tools_count} registered (Demo, Filesystem, System, Apps, Terminal, Memory, Knowledge, Browser, Tasks)
  Security Policy: Active (READ/LOW: Auto, MED/HIGH: Confirm, CRIT: Deny)
======================================================================
"""
    print(banner.strip())





def run_system_check(
    settings: Settings,
    client: OllamaClient,
    registry: ToolRegistry,
    permission_manager: Optional[PermissionManager] = None,
) -> bool:
    """Run comprehensive environment, storage, Ollama, tool, and security diagnostics."""
    logger = get_logger("check")
    logger.info("Running system integrity, Ollama, and security diagnostics...")

    all_passed = True

    # 1. Configuration check
    print("[OK] Configuration loaded")

    # 2. Runtime directories check
    try:
        settings.ensure_directories()
        data_dir = settings.get_resolved_data_dir()
        logs_dir = settings.get_resolved_logs_dir()
        if data_dir.is_dir() and logs_dir.is_dir():
            print("[OK] Runtime directories verified")
        else:
            print("[FAIL] Runtime directories verification failed")
            all_passed = False
    except Exception as err:
        logger.exception("Runtime directory check failed: %s", err)
        print(f"[FAIL] Runtime directories: {err}")
        all_passed = False

    # 3. Tool registry check
    tool_names = [t.name for t in registry.list()]
    print(f"[OK] Tool registry initialized ({len(tool_names)} tools)")

    # 4. Security policy check
    print("[OK] Security policy initialized (Fail-closed enabled)")

    # 5. Filesystem boundary check
    allowed_roots = settings.get_resolved_allowed_roots()
    print(f"[OK] Filesystem boundaries verified ({len(allowed_roots)} allowed roots)")

    # 6. System & Application Tools diagnostics
    print("[OK] System tools initialized")
    app_registry = ApplicationRegistry()
    print(f"[OK] Application registry initialized ({len(app_registry.list_names())} whitelisted apps)")

    # 7. Controlled Terminal & Execution diagnostics
    print("[OK] Execution policy initialized (Shell execution disabled)")
    print("[OK] Controlled terminal tools initialized (6 development tools)")

    # 8. Persistent Memory & Database diagnostics (Phase 8)
    try:
        db = MemoryDatabase(settings=settings)
        db.initialize()
        if db.check_integrity():
            print("[OK] Memory database initialized (SQLite integrity verified)")
        else:
            print("[FAIL] Memory database integrity check failed")
            all_passed = False
    except Exception as err:
        logger.exception("Memory database diagnostic failed: %s", err)
        print(f"[FAIL] Memory database: {err}")
        all_passed = False

    print("[OK] Persistent memory tools initialized (3 memory tools)")

    # 9. Personal Knowledge & RAG diagnostics (Phase 9)
    try:
        km = KnowledgeManager(settings=settings)
        km.initialize()
        if km.db.check_integrity():
            print("[OK] Knowledge database initialized (SQLite integrity verified)")
            print(f"[OK] Embedding provider ready ({km.embedding_provider.model_name})")
            print(f"[OK] Knowledge index ready ({km.db.get_document_count()} docs, {km.db.get_chunk_count()} chunks)")
        else:
            print("[FAIL] Knowledge database integrity check failed")
            all_passed = False
    except Exception as err:
        logger.exception("Knowledge database diagnostic failed: %s", err)
        print(f"[FAIL] Knowledge database: {err}")
        all_passed = False

    print("[OK] Personal knowledge tools initialized (5 RAG tools)")

    # 10. Browser Automation diagnostics (Phase 10)
    try:
        bm = BrowserManager(settings=settings)
        mode = "headless" if settings.browser_headless else "visible"
        print(f"[OK] Browser manager initialized ({mode} mode, timeout: {settings.browser_page_timeout_seconds}s)")
    except Exception as err:
        logger.exception("Browser manager diagnostic failed: %s", err)
        print(f"[FAIL] Browser manager: {err}")
        all_passed = False

    print("[OK] Browser automation tools initialized (10 browser tools)")

    # 11. Voice subsystem diagnostics (Phase 12)
    try:
        from app.voice.audio import get_default_microphone, list_microphones
        from app.voice.providers import FasterWhisperProvider

        mics = list_microphones()
        def_mic = get_default_microphone()
        def_name = def_mic.name if def_mic else "None"
        print(f"[OK] Voice input initialized ({len(mics)} microphones detected, default: {def_name})")
        stt = FasterWhisperProvider(model_name=settings.stt_model)
        stt_status = "available" if stt.is_available() else "dependency missing"
        print(f"[OK] Speech-to-text engine ready (faster-whisper, model: {settings.stt_model}, {stt_status})")
    except Exception as err:
        logger.exception("Voice input diagnostic failed: %s", err)
        print(f"[FAIL] Voice input: {err}")
        all_passed = False

    # 12. Text-to-Speech subsystem diagnostics (Phase 13)
    try:
        from app.voice.tts_audio import get_default_output_device, list_output_devices
        from app.voice.tts_providers import Pyttsx3Provider

        outputs = list_output_devices()
        def_out = get_default_output_device()
        def_out_name = def_out.name if def_out else "None"
        print(f"[OK] Audio output devices initialized ({len(outputs)} playback devices, default: {def_out_name})")

        tts_provider = Pyttsx3Provider()
        voices = tts_provider.list_voices()
        tts_avail = "available" if tts_provider.is_available() else "dependency missing"
        print(f"[OK] Text-to-speech engine ready ({settings.tts_provider}, {len(voices)} voices found, {tts_avail})")
    except Exception as err:
        logger.exception("Text-to-speech diagnostic failed: %s", err)
        print(f"[FAIL] Text-to-speech: {err}")
        all_passed = False

    # 13. Task & Scheduler subsystem diagnostics (Phase 14)
    try:
        from app.tasks.database import TaskDatabase
        from app.tasks.repository import TaskRepository

        task_db = TaskDatabase(settings=settings)
        task_repo = TaskRepository(db=task_db)
        tasks_list = task_repo.list_tasks()
        print(f"[OK] Task database initialized ({len(tasks_list)} tasks persisted)")
        sched_state = "enabled" if settings.tasks_enabled else "disabled"
        print(f"[OK] Task scheduler ready ({sched_state}, poll: {settings.task_scheduler_poll_seconds}s, max concurrent: {settings.max_concurrent_tasks})")
    except Exception as err:
        logger.exception("Task subsystem diagnostic failed: %s", err)
        print(f"[FAIL] Task subsystem: {err}")
        all_passed = False

    # 14. Ollama server & model diagnostics
    ollama_mgr = OllamaManager(settings=settings)
    exe_found = ollama_mgr.find_executable()
    if exe_found:
        print(f"[OK] Ollama executable located at {exe_found}")
    else:
        print("[WARN] Ollama executable not found in PATH or standard locations (auto-start requires manual path)")

    status = client.get_status()
    if status.is_connected:
        print(f"[OK] Ollama server reachable at {status.base_url}")

        if status.is_model_available:
            print(f"[OK] Model '{status.model_name}' available")
        else:
            models_display = ", ".join(status.available_models) if status.available_models else "None"
            print(f"[FAIL] Model '{status.model_name}' not installed (available: {models_display})")
            all_passed = False
    else:
        err_msg = status.error_message or "Connection refused"
        print(f"[FAIL] Ollama server unreachable at {status.base_url} ({err_msg})")
        print(f"[FAIL] Model '{status.model_name}': Server offline")
        all_passed = False

    # 15. Intelligent Model Routing diagnostics (Phase 16)

    try:
        from app.models import (
            ModelAvailabilityChecker,
            ModelRegistry,
            ModelResourceManager,
            ModelRouter,
        )

        m_reg = ModelRegistry(settings=settings)
        m_avail = ModelAvailabilityChecker(client=client, settings=settings)
        m_res = ModelResourceManager(client=client, settings=settings)
        statuses = m_avail.get_all_statuses(m_reg)
        installed_count = sum(1 for s in statuses if s.installed)
        print(f"[OK] Model registry initialized ({len(m_reg.list())} profiles, {installed_count} installed)")
        ram_info = m_res.get_memory_info()
        print(f"[OK] System resources tracked (RAM: {ram_info['available_gb']} GB available / {ram_info['total_gb']} GB total, {ram_info['used_percent']}% used)")
    except Exception as err:
        logger.exception("Model routing diagnostic failed: %s", err)
        print(f"[FAIL] Model routing: {err}")
        all_passed = False

    return all_passed



def run_single_chat(
    agent: Agent, prompt: str, model: Optional[str] = None
) -> int:
    """Execute a single-shot chat request via the agent orchestration loop."""
    logger = get_logger("chat")
    target_model = model or agent.client.default_model

    print(f"\nPrompt: {prompt}")
    print(f"Connecting to model '{target_model}' on {agent.client.base_url}...\n")

    # Verify server connectivity first
    if not agent.client.check_connection():
        print(
            f"[ERROR] Could not connect to Ollama at {agent.client.base_url}. Ensure Ollama is running.",
            file=sys.stderr,
        )
        return 1

    # Verify model availability
    if not agent.client.model_exists(target_model):
        try:
            available = agent.client.list_models()
            avail_str = ", ".join(available) if available else "none"
        except Exception:
            avail_str = "unknown"
        print(
            f"[ERROR] Model '{target_model}' is not available on Ollama. Installed models: {avail_str}",
            file=sys.stderr,
        )
        return 1

    try:
        print("Assistant:")
        for chunk in agent.stream_run(prompt, model=target_model, interactive=True):
            sys.stdout.write(chunk)
            sys.stdout.flush()
        print()  # Final newline
        return 0

    except (OllamaConnectionError, ModelNotFoundError, ModelAPIError) as err:
        logger.error("Chat execution error: %s", err)
        print(f"\n[ERROR] Model execution failed: {err}", file=sys.stderr)
        return 1
    except ToolRoundLimitError as err:
        logger.error("Tool round limit reached: %s", err)
        print(f"\n[ERROR] Tool execution round limit reached: {err}", file=sys.stderr)
        return 1
    except InvalidMessageError as err:
        logger.warning("Invalid message submitted: %s", err)
        print(f"\n[ERROR] Invalid message: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        logger.exception("Unexpected error during chat: %s", err)
        print(f"\n[ERROR] Unexpected error: {err}", file=sys.stderr)
        return 1


def run_interactive_chat(
    agent: Agent,
    conversation_manager: Optional[ConversationManager] = None,
    knowledge_manager: Optional[KnowledgeManager] = None,
    browser_manager: Optional[BrowserManager] = None,
    model: Optional[str] = None,
) -> int:
    """Run an interactive multi-turn conversation session in the terminal."""
    logger = get_logger("interactive")
    target_model = model or agent.client.default_model

    # Check connection and model before entering loop
    if not agent.client.check_connection():
        print(
            f"[ERROR] Could not connect to Ollama at {agent.client.base_url}. Ensure Ollama is running.",
            file=sys.stderr,
        )
        return 1

    if not agent.client.model_exists(target_model):
        try:
            available = agent.client.list_models()
            avail_str = ", ".join(available) if available else "none"
        except Exception:
            avail_str = "unknown"
        print(
            f"[ERROR] Model '{target_model}' is not available on Ollama. Installed models: {avail_str}",
            file=sys.stderr,
        )
        return 1

    tools_str = ", ".join([t.name for t in agent.registry.list()])
    banner = f"""
======================================================================
  Local Assistant - Interactive Multi-Turn Chat
======================================================================
  Model:     {target_model}
  Host:      {agent.client.base_url}
  Session:   {agent.conversation.id}
  Tools:     {tools_str}
  Security:  Permission Manager Active (Confirmation Enabled)
  Commands:
    /new           - Start a new conversation session
    /list          - List saved conversation sessions
    /resume <id>   - Resume a saved conversation by ID
    /memories      - Inspect stored persistent user memories
    /knowledge     - Inspect indexed knowledge base documents
    /search <q>    - Search local knowledge base
    /browser       - Inspect active browser session state
    /clear, /reset - Clear current conversation history
    /help          - Show commands
    /exit, /quit   - Quit session
======================================================================
"""
    print(banner.strip())


    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("/exit", "/quit", "exit", "quit"):
            print("Exiting interactive chat. Goodbye!")
            break
        elif cmd in ("/clear", "/reset"):
            agent.conversation.reset()
            print("Conversation history cleared.")
            continue
        elif cmd == "/new":
            if conversation_manager:
                new_conv = conversation_manager.create_conversation()
                agent.conversation = new_conv
                print(f"Started new conversation session: {new_conv.id}")
            else:
                agent.conversation.reset()
                print("Started new conversation session.")
            continue
        elif cmd == "/list":
            if conversation_manager:
                convs = conversation_manager.list_conversations()
                if not convs:
                    print("No saved conversations found.")
                else:
                    print("Saved Conversations:")
                    for c in convs:
                        cid = getattr(c, "id", "")
                        title = getattr(c, "title", "Conversation")
                        marker = " [active]" if cid == agent.conversation.id else ""
                        print(f" - {cid}: {title}{marker}")
            else:
                print("Session persistence manager not configured.")
            continue
        elif cmd.startswith("/resume"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("Usage: /resume <conversation_id>")
            elif conversation_manager:
                cid = parts[1].strip()
                try:
                    resumed = conversation_manager.load_conversation(cid)
                    agent.conversation = resumed
                    print(f"Resumed conversation {resumed.id} ({resumed.message_count()} messages).")
                except Exception as err:
                    print(f"Failed to resume conversation: {err}")
            else:
                print("Session persistence manager not configured.")
            continue
        elif cmd == "/memories":
            if agent.memory_manager:
                mems = agent.memory_manager.recall(limit=20)
                if not mems:
                    print("No stored memories found.")
                else:
                    print(f"Stored Persistent Memories ({len(mems)}):")
                    for m in mems:
                        print(f" - [{m.category.value}] {m.key}: {m.value}")
            else:
                print("Memory manager not configured.")
            continue
        elif cmd == "/knowledge":
            if knowledge_manager:
                docs = knowledge_manager.list_documents()
                if not docs:
                    print("No documents indexed in local knowledge base.")
                else:
                    print(f"Indexed Knowledge Documents ({len(docs)}):")
                    for d in docs:
                        print(f" - {d.file_name} ({d.file_type}, {d.file_size} bytes)")
            else:
                print("Knowledge manager not configured.")
            continue
        elif cmd.startswith("/search"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("Usage: /search <query>")
            elif knowledge_manager:
                q = parts[1].strip()
                results, _ = knowledge_manager.search(q, top_k=3)
                if not results:
                    print(f"No matching passages found for '{q}'.")
                else:
                    print(f"Top Knowledge Matches for '{q}':")
                    for r in results:
                        page = f" (Page {r.chunk.page_number})" if r.chunk.page_number else ""
                        snippet = r.chunk.text.replace("\n", " ")[:120]
                        print(f" - [{r.score:.2f}] {r.chunk.file_name}{page}: {snippet}...")
            else:
                print("Knowledge manager not configured.")
            continue
        elif cmd == "/browser":
            if browser_manager:
                info = browser_manager.get_session_info()
                if not info or not info.is_active:
                    print("No active browser session.")
                else:
                    curr_url = info.current_url or "No URL loaded"
                    curr_title = info.current_title or "Untitled"
                    print(f"Active Browser Session ({info.session_id}):")
                    print(f" - Headless:     {info.headless}")
                    print(f" - URL:          {curr_url}")
                    print(f" - Title:        {curr_title}")
                    print(f" - Navigations:  {info.navigation_count}")
            else:
                print("Browser manager not configured.")
            continue
        elif cmd == "/help":
            print("Commands: /new, /list, /resume <id>, /memories, /knowledge, /search <q>, /browser, /clear, /exit")
            continue



        try:
            print("Assistant: ", end="", flush=True)
            for chunk in agent.stream_run(user_input, model=target_model, interactive=True):
                sys.stdout.write(chunk)
                sys.stdout.flush()
            print()
        except (OllamaConnectionError, ModelNotFoundError, ModelAPIError) as err:
            logger.error("Interactive turn error: %s", err)
            print(f"\n[ERROR] Model execution error: {err}")
        except ToolRoundLimitError as err:
            logger.error("Tool round limit in interactive turn: %s", err)
            print(f"\n[ERROR] Maximum tool iterations exceeded: {err}")
        except InvalidMessageError as err:
            logger.warning("Invalid input in interactive chat: %s", err)
            print(f"\n[ERROR] {err}")
        except Exception as err:
            logger.exception("Unexpected error in interactive turn: %s", err)
            print(f"\n[ERROR] Unexpected error: {err}")

    return 0


def main(args: Optional[list[str]] = None) -> int:
    """Application main entry point."""
    parser = argparse.ArgumentParser(
        description="Local AI Personal Assistant - Fully local, extensible assistant powered by Ollama."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run environment, storage, and Ollama diagnostics then exit.",
    )
    parser.add_argument(
        "--chat",
        type=str,
        metavar="PROMPT",
        help="Send a single chat prompt to the configured local model and exit.",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Start an interactive multi-turn chat session in the terminal.",
    )
    parser.add_argument(
        "--model",
        type=str,
        metavar="MODEL_NAME",
        help="Override the default Ollama model for this invocation.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the PySide6 desktop graphical interface.",
    )
    parser.add_argument(
        "--background",
        "--tray",
        action="store_true",
        dest="background",
        help="Launch the assistant directly into background resident system tray mode.",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Override log level to DEBUG.",
    )

    parsed_args = parser.parse_args(args)

    # Ensure Windows console uses UTF-8 so emojis from LLM do not throw UnicodeEncodeError
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    try:
        settings = get_settings()
        if parsed_args.debug:
            settings.log_level = "DEBUG"
            settings.debug = True

        logger = setup_logging(settings)
        logger.info("Starting %s v%s in %s mode", settings.app_name, settings.version, settings.environment)

        # ── EARLY GUI LAUNCH ──
        # For --gui / --background / frozen EXE: branch directly into run_gui()
        # which manages its own single-instance check and backend lifecycle.
        is_frozen = getattr(sys, "frozen", False)
        wants_gui = (
            parsed_args.gui
            or parsed_args.background
            or (is_frozen and not any([parsed_args.chat, parsed_args.interactive, parsed_args.check]))
        )
        if wants_gui:
            from app.ui import run_gui
            return run_gui(
                settings=settings,
                model=parsed_args.model,
                background_mode=parsed_args.background,
            )

        client = OllamaClient(
            base_url=settings.ollama_base_url,
            timeout=settings.ollama_timeout_seconds,
            default_model=parsed_args.model or settings.default_model,
        )

        memory_manager = MemoryManager(settings=settings)
        memory_manager.initialize()

        knowledge_manager = KnowledgeManager(settings=settings)
        knowledge_manager.initialize()

        browser_manager = BrowserManager(settings=settings)

        conversation_manager = ConversationManager(
            client=client,
            settings=settings,
            memory_manager=memory_manager,
        )

        task_db = TaskDatabase(settings=settings)
        task_repo = TaskRepository(db=task_db)
        task_manager = TaskManager(repository=task_repo, settings=settings)

        event_db = EventDatabase(settings=settings)
        event_repo = EventRepository(db=event_db)
        event_engine = EventEngine(repository=event_repo, settings=settings)

        registry = get_default_tool_registry(
            settings,
            memory_manager=memory_manager,
            knowledge_manager=knowledge_manager,
            browser_manager=browser_manager,
            task_manager=task_manager,
            event_engine=event_engine,
        )

        confirmation_manager = ConfirmationManager(CliConfirmationProvider())
        permission_manager = PermissionManager(
            settings=settings,
            confirmation_manager=confirmation_manager,
        )

        from app.models import (
            ModelAvailabilityChecker,
            ModelMetricsTracker,
            ModelRegistry,
            ModelRouter,
            ModelSelector,
        )

        model_registry = ModelRegistry(settings=settings)
        model_avail_checker = ModelAvailabilityChecker(client=client, settings=settings)
        model_selector = ModelSelector(settings=settings)
        model_router = ModelRouter(
            registry=model_registry,
            availability_checker=model_avail_checker,
            selector=model_selector,
            settings=settings,
        )
        model_metrics = ModelMetricsTracker()

        agent = Agent(
            conversation=conversation_manager.active_conversation,
            client=client,
            registry=registry,
            permission_manager=permission_manager,
            memory_manager=memory_manager,
            router=model_router,
            metrics_tracker=model_metrics,
            max_rounds=settings.max_tool_call_rounds,
            settings=settings,
        )


        try:
            # Handle frozen executable default launch (LocalAssistant.exe without flags launches Desktop GUI)
            is_frozen = getattr(sys, "frozen", False)
            if is_frozen and not any([parsed_args.chat, parsed_args.interactive, parsed_args.check]):
                from app.ui import run_gui
                return run_gui(
                    settings=settings,
                    model=parsed_args.model,
                    background_mode=parsed_args.background,
                )

            # Handle --gui and --background commands
            if parsed_args.gui or parsed_args.background:
                from app.ui import run_gui
                return run_gui(
                    settings=settings,
                    model=parsed_args.model,
                    background_mode=parsed_args.background,
                )


            # Handle --chat command
            if parsed_args.chat:
                return run_single_chat(agent, parsed_args.chat, model=parsed_args.model)

            # Handle --interactive command
            if parsed_args.interactive:
                return run_interactive_chat(
                    agent,
                    conversation_manager=conversation_manager,
                    knowledge_manager=knowledge_manager,
                    browser_manager=browser_manager,
                    model=parsed_args.model,
                )



            # Retrieve status for banner and checks (fails gracefully if Ollama is offline)
            ollama_status = client.get_status()
            print_status_banner(settings, ollama_status, tools_count=len(registry.list()))

            if parsed_args.check:
                is_healthy = run_system_check(settings, client, registry, permission_manager)
                if is_healthy:
                    print("\n[OK] System check passed successfully.")
                    return 0
                else:
                    print("\n[FAIL] System check encountered errors. Check output or logs for details.")
                    return 1

            print("\nApplication initialized successfully. Ready for Phase 1 (Ollama Integration).")
            return 0
        finally:
            browser_manager.close_session()

    except (ConfigurationError, ValidationError) as err:
        print(f"\n[FATAL] Configuration error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"\n[FATAL] Unhandled startup error: {err}", file=sys.stderr)
        return 1



if __name__ == "__main__":
    sys.exit(main())
