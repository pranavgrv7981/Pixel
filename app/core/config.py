"""Configuration management for the Local AI Personal Assistant."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import AliasChoices, Field, field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_build_commit() -> str:
    """Retrieve git short commit SHA or build identifier."""
    try:
        import subprocess
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "e571b03"


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Application
    app_name: str = Field(default="Local AI Personal Assistant", description="Application display name")
    version: str = Field(default="0.1.0", description="Application version")
    build_commit: str = Field(default_factory=get_build_commit, description="Git commit short SHA for build identification")
    environment: Literal["development", "production", "test"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
        description="Running environment",
    )

    debug: bool = Field(default=False, description="Enable debug mode")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    log_to_file: bool = Field(default=True, description="Enable logging to file")
    log_to_console: bool = Field(default=True, description="Enable logging to standard console")
    log_file_name: str = Field(default="assistant.log", description="Log file name")

    # Storage Paths
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent,
        description="Project root directory path",
    )
    data_dir: Path = Field(default=Path("data"), description="Path to runtime persistent data directory")
    logs_dir: Path = Field(default=Path("logs"), description="Path to log directory")

    # Model / Ollama Settings
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama API base URL")
    default_model: str = Field(default="qwen3:30b", description="Default model name for Ollama")
    ollama_timeout_seconds: float = Field(default=300.0, description="Ollama request timeout in seconds")
    ollama_connect_timeout_seconds: float = Field(default=10.0, description="Ollama TCP connect timeout in seconds")
    ollama_stall_timeout_seconds: float = Field(default=180.0, description="Timeout for idle stream without new tokens")
    ollama_generation_timeout_seconds: float = Field(default=600.0, description="Maximum total generation time permitted")
    ollama_num_ctx: int = Field(
        default=4096,
        validation_alias=AliasChoices("OLLAMA_NUM_CTX", "NUM_CTX"),
        description="Ollama context window token size",
    )


    # Conversation Engine Settings (Phase 2)
    max_conversation_messages: int = Field(
        default=50,
        validation_alias=AliasChoices("MAX_CONVERSATION_MESSAGES", "MAX_MESSAGES"),
        description="Maximum number of conversational messages retained in memory",
    )
    system_prompt: str = Field(
        default="You are a helpful local AI personal assistant.",
        validation_alias=AliasChoices("SYSTEM_PROMPT"),
        description="Default system prompt prepended to conversation context",
    )

    # Tool Calling Settings (Phase 3)
    max_tool_call_rounds: int = Field(
        default=5,
        validation_alias=AliasChoices("MAX_TOOL_CALL_ROUNDS"),
        description="Maximum sequential rounds of tool calls allowed per turn",
    )

    # Permission and Safety Settings (Phase 4)
    auto_approve_read_tools: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTO_APPROVE_READ_TOOLS"),
        description="Automatically approve tools classified as READ risk without prompt",
    )
    auto_approve_low_risk_tools: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTO_APPROVE_LOW_RISK_TOOLS"),
        description="Automatically approve tools classified as LOW risk without prompt",
    )
    require_confirmation_medium: bool = Field(
        default=True,
        validation_alias=AliasChoices("REQUIRE_CONFIRMATION_MEDIUM"),
        description="Require explicit user confirmation for MEDIUM risk tool actions",
    )
    require_confirmation_high: bool = Field(
        default=True,
        validation_alias=AliasChoices("REQUIRE_CONFIRMATION_HIGH"),
        description="Require explicit user confirmation for HIGH risk tool actions",
    )
    allow_critical_tools: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLOW_CRITICAL_TOOLS"),
        description="Permit CRITICAL risk tools to execute (defaults to false for safety)",
    )

    # File-System Settings (Phase 5)
    filesystem_allowed_roots: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("FILESYSTEM_ALLOWED_ROOTS"),
        description="Allowed root directory paths accessible to file-system tools",
    )
    filesystem_protected_paths: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("FILESYSTEM_PROTECTED_PATHS"),
        description="Protected paths that file tools are prohibited from modifying or deleting",
    )
    max_file_read_bytes: int = Field(
        default=1048576,  # 1 MB
        validation_alias=AliasChoices("MAX_FILE_READ_BYTES"),
        description="Maximum bytes to read from a single file before truncating",
    )
    max_file_write_bytes: int = Field(
        default=1048576,  # 1 MB
        validation_alias=AliasChoices("MAX_FILE_WRITE_BYTES"),
        description="Maximum bytes permitted for a single file write operation",
    )
    max_search_results: int = Field(
        default=100,
        validation_alias=AliasChoices("MAX_SEARCH_RESULTS"),
        description="Maximum matching entries returned by search_files",
    )
    max_list_results: int = Field(
        default=200,
        validation_alias=AliasChoices("MAX_LIST_RESULTS"),
        description="Maximum directory items returned by list_directory",
    )

    # System and Application Settings (Phase 6)
    max_process_results: int = Field(
        default=100,
        validation_alias=AliasChoices("MAX_PROCESS_RESULTS"),
        description="Maximum number of processes returned by list_running_processes",
    )
    application_launch_timeout_seconds: float = Field(
        default=3.0,
        validation_alias=AliasChoices("APPLICATION_LAUNCH_TIMEOUT_SECONDS"),
        description="Maximum seconds to wait for application launch verification",
    )
    application_close_timeout_seconds: float = Field(
        default=3.0,
        validation_alias=AliasChoices("APPLICATION_CLOSE_TIMEOUT_SECONDS"),
        description="Maximum seconds to wait for application exit verification",
    )

    # Controlled Terminal & Execution Settings (Phase 7)
    command_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("COMMAND_TIMEOUT_SECONDS"),
        description="Maximum seconds permitted for controlled command execution before timing out",
    )
    max_command_output_bytes: int = Field(
        default=65536,
        validation_alias=AliasChoices("MAX_COMMAND_OUTPUT_BYTES"),
        description="Maximum captured output bytes per command execution before truncation (default 64 KB)",
    )
    python_executable: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("PYTHON_EXECUTABLE"),
        description="Optional path to trusted Python interpreter executable",
    )
    compiler_executable: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("COMPILER_EXECUTABLE"),
        description="Optional path to trusted C compiler executable (e.g. gcc, clang)",
    )
    git_executable: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GIT_EXECUTABLE"),
        description="Optional path to trusted Git executable",
    )

    # Persistent Memory Settings (Phase 8)
    memory_database_path: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("MEMORY_DATABASE_PATH"),
        description="Path to persistent SQLite memory database file (defaults to data/assistant.db)",
    )
    max_persisted_messages: int = Field(
        default=500,
        validation_alias=AliasChoices("MAX_PERSISTED_MESSAGES"),
        description="Maximum messages retained in persistent conversation history",
    )
    max_recalled_memories: int = Field(
        default=5,
        validation_alias=AliasChoices("MAX_RECALLED_MEMORIES"),
        description="Maximum relevant memories retrieved for context injection",
    )

    # Personal Knowledge / RAG Settings (Phase 9)
    knowledge_data_dir: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("KNOWLEDGE_DATA_DIR"),
        description="Directory for RAG knowledge database and indexes (defaults to data/knowledge)",
    )
    knowledge_database_path: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("KNOWLEDGE_DATABASE_PATH"),
        description="Path to SQLite knowledge database (defaults to data/knowledge/knowledge.db)",
    )
    embedding_provider: str = Field(
        default="local",
        validation_alias=AliasChoices("EMBEDDING_PROVIDER"),
        description="Embedding provider to use: 'local' (deterministic offline) or 'ollama'",
    )
    embedding_model: str = Field(
        default="local-hash-384",
        validation_alias=AliasChoices("EMBEDDING_MODEL"),
        description="Name of the embedding model representation (default 'local-hash-384' or 'nomic-embed-text')",
    )
    chunk_size: int = Field(
        default=1000,
        validation_alias=AliasChoices("CHUNK_SIZE"),
        description="Target character chunk size for document chunking",
    )
    chunk_overlap: int = Field(
        default=150,
        validation_alias=AliasChoices("CHUNK_OVERLAP"),
        description="Character overlap between consecutive chunks",
    )
    rag_top_k: int = Field(
        default=4,
        validation_alias=AliasChoices("RAG_TOP_K"),
        description="Maximum number of chunks retrieved per knowledge search",
    )
    rag_min_score: float = Field(
        default=0.25,
        validation_alias=AliasChoices("RAG_MIN_SCORE"),
        description="Minimum relevance score threshold for retrieval",
    )
    max_rag_context_chunks: int = Field(
        default=4,
        validation_alias=AliasChoices("MAX_RAG_CONTEXT_CHUNKS"),
        description="Maximum retrieved chunks injected into prompt context",
    )
    max_rag_context_bytes: int = Field(
        default=8192,
        validation_alias=AliasChoices("MAX_RAG_CONTEXT_BYTES"),
        description="Maximum total bytes of retrieved context injected into prompt",
    )
    max_indexed_files_per_operation: int = Field(
        default=50,
        validation_alias=AliasChoices("MAX_INDEXED_FILES_PER_OPERATION"),
        description="Maximum files indexed in a single operation/directory crawl",
    )
    max_document_size_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias=AliasChoices("MAX_DOCUMENT_SIZE_BYTES"),
        description="Maximum file size in bytes permitted for document indexing (default 10 MB)",
    )

    # Browser Automation Settings (Phase 10)
    browser_headless: bool = Field(
        default=True,
        validation_alias=AliasChoices("BROWSER_HEADLESS"),
        description="Whether to run the browser in headless mode",
    )
    browser_page_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("BROWSER_PAGE_TIMEOUT_SECONDS"),
        description="Maximum seconds to wait for page load navigation",
    )
    browser_action_timeout_seconds: float = Field(
        default=15.0,
        validation_alias=AliasChoices("BROWSER_ACTION_TIMEOUT_SECONDS"),
        description="Maximum seconds to wait for a browser click/type action",
    )
    browser_session_timeout_seconds: float = Field(
        default=900.0,
        validation_alias=AliasChoices("BROWSER_SESSION_TIMEOUT_SECONDS"),
        description="Maximum idle seconds before an inactive browser session automatically closes",
    )
    max_browser_text_bytes: int = Field(
        default=32768,
        validation_alias=AliasChoices("MAX_BROWSER_TEXT_BYTES"),
        description="Maximum bytes of text extracted from a webpage for model context",
    )
    max_browser_elements: int = Field(
        default=100,
        validation_alias=AliasChoices("MAX_BROWSER_ELEMENTS"),
        description="Maximum interactive elements extracted per page snapshot",
    )
    allow_local_network: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLOW_LOCAL_NETWORK"),
        description="Whether the browser is permitted to navigate to private IP ranges and localhost",
    )

    # Voice Input Settings (Phase 12)
    voice_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("VOICE_ENABLED"),
        description="Whether local speech-to-text voice input is enabled",
    )
    stt_model: str = Field(
        default="base",
        validation_alias=AliasChoices("STT_MODEL"),
        description="Faster-Whisper model name: 'tiny', 'base', 'small', 'medium'",
    )
    stt_device: str = Field(
        default="cpu",
        validation_alias=AliasChoices("STT_DEVICE"),
        description="Device for STT inference ('cpu' or 'cuda')",
    )
    stt_compute_type: str = Field(
        default="int8",
        validation_alias=AliasChoices("STT_COMPUTE_TYPE"),
        description="Quantization compute type for STT ('int8', 'float16', 'float32')",
    )
    audio_sample_rate: int = Field(
        default=16000,
        validation_alias=AliasChoices("AUDIO_SAMPLE_RATE"),
        description="Target sample rate in Hz for audio capture",
    )
    max_recording_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices("MAX_RECORDING_SECONDS"),
        description="Maximum recording duration in seconds before automatic stop",
    )
    selected_microphone: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SELECTED_MICROPHONE"),
        description="Name or substring of the preferred microphone device",
    )

    # Pixel Activation & Summoning Settings (Pixel Feature)
    pixel_name: str = Field(
        default="Pixel",
        validation_alias=AliasChoices("PIXEL_NAME"),
        description="Permanent name/identity of the assistant",
    )
    global_hotkey: str = Field(
        default="Alt+P",
        validation_alias=AliasChoices("GLOBAL_HOTKEY"),
        description="Global system-wide hotkey to summon Pixel",
    )
    voice_wake_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("VOICE_WAKE_ENABLED"),
        description="Whether continuous low-resource voice wake listening is active (default false)",
    )
    voice_activation_phrase: str = Field(
        default="Pixel",
        validation_alias=AliasChoices("VOICE_ACTIVATION_PHRASE"),
        description="Voice activation trigger phrase for summoning Pixel",
    )
    voice_wake_feedback: bool = Field(
        default=True,
        validation_alias=AliasChoices("VOICE_WAKE_FEEDBACK"),
        description="Whether to provide quick local TTS voice feedback ('Ready.') when summoned by voice",
    )

    # Local Text-to-Speech Settings (Phase 13)
    tts_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("TTS_ENABLED"),
        description="Whether local text-to-speech synthesis is enabled",
    )
    tts_provider: str = Field(
        default="pyttsx3",
        validation_alias=AliasChoices("TTS_PROVIDER"),
        description="Text-to-speech engine provider ('pyttsx3' or 'piper')",
    )
    tts_voice: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TTS_VOICE"),
        description="Voice identifier or name substring for speech synthesis",
    )
    tts_speed_rate: int = Field(
        default=175,
        validation_alias=AliasChoices("TTS_SPEED_RATE"),
        description="Speaking rate in words per minute (e.g. 100-250)",
    )
    auto_speak_responses: bool = Field(
        default=False,
        validation_alias=AliasChoices("AUTO_SPEAK_RESPONSES"),
        description="Whether to automatically speak new assistant responses upon completion",
    )
    max_tts_characters: int = Field(
        default=1500,
        validation_alias=AliasChoices("MAX_TTS_CHARACTERS"),
        description="Maximum characters synthesized in a single speech utterance segment",
    )
    selected_audio_output: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SELECTED_AUDIO_OUTPUT"),
        description="Name or substring of the preferred audio output device (speaker/headphones)",
    )

    # Local Ollama Management & Packaging Settings (Phase 14)
    ollama_executable: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OLLAMA_EXECUTABLE"),
        description="Explicit path to ollama executable",
    )
    auto_start_ollama: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTO_START_OLLAMA"),
        description="Automatically start Ollama background server if not already running",
    )
    stop_ollama_on_exit: bool = Field(
        default=False,
        validation_alias=AliasChoices("STOP_OLLAMA_ON_EXIT"),
        description="Stop Ollama server on application exit only if started by this app",
    )
    preload_model: bool = Field(
        default=False,
        validation_alias=AliasChoices("PRELOAD_MODEL"),
        description="Warm up model into memory on startup",
    )
    ollama_keep_alive: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OLLAMA_KEEP_ALIVE"),
        description="Duration to keep model in Ollama VRAM (e.g. '5m', '15m', '-1')",
    )
    minimize_to_tray: bool = Field(
        default=True,
        validation_alias=AliasChoices("MINIMIZE_TO_TRAY"),
        description="Minimize to system tray on window close",
    )
    start_with_windows: bool = Field(
        default=False,
        validation_alias=AliasChoices("START_WITH_WINDOWS"),
        description="Register to start on Windows user login",
    )
    single_instance_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("SINGLE_INSTANCE_ENABLED"),
        description="Enforce single application instance via named mutex / socket",
    )
    max_event_chain_depth: int = Field(
        default=3,
        validation_alias=AliasChoices("MAX_EVENT_CHAIN_DEPTH"),
        description="Max event chain depth to prevent cascade loops",
    )

    # Tasks, Scheduling and Automation Settings (Phase 14)
    tasks_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("TASKS_ENABLED"),
        description="Whether persistent task scheduling and background triggers are enabled",
    )
    automation_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTOMATION_ENABLED"),
        description="Master switch for background event engine and real-time triggers",
    )
    start_in_background: bool = Field(
        default=False,
        validation_alias=AliasChoices("START_IN_BACKGROUND"),
        description="Whether the application launches minimized directly to the system tray",
    )
    max_active_triggers: int = Field(
        default=20,
        validation_alias=AliasChoices("MAX_ACTIVE_TRIGGERS"),
        description="Maximum number of active background triggers",
    )
    max_event_history: int = Field(
        default=100,
        validation_alias=AliasChoices("MAX_EVENT_HISTORY"),
        description="Maximum recent event history records stored in memory/database",
    )
    max_events_per_second: int = Field(
        default=20,
        validation_alias=AliasChoices("MAX_EVENTS_PER_SECOND"),
        description="Rate limit cap on incoming events processed per second",
    )
    file_watch_debounce_ms: int = Field(
        default=500,
        validation_alias=AliasChoices("FILE_WATCH_DEBOUNCE_MS"),
        description="Debounce time window in milliseconds for coalescing rapid filesystem events",
    )
    system_monitor_interval_seconds: float = Field(
        default=5.0,
        validation_alias=AliasChoices("SYSTEM_MONITOR_INTERVAL_SECONDS"),
        description="Sampling interval in seconds for local CPU/RAM/Battery metrics",
    )
    default_trigger_cooldown_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("DEFAULT_TRIGGER_COOLDOWN_SECONDS"),
        description="Default suppression cooldown in seconds after a trigger fires",
    )
    speak_background_notifications: bool = Field(
        default=False,
        validation_alias=AliasChoices("SPEAK_BACKGROUND_NOTIFICATIONS"),
        description="Whether to speak background trigger notifications via TTS (disabled by default)",
    )
    max_concurrent_tasks: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_CONCURRENT_TASKS"),
        description="Maximum concurrent scheduled task worker executions",
    )
    task_scheduler_poll_seconds: float = Field(
        default=2.0,
        validation_alias=AliasChoices("TASK_SCHEDULER_POLL_SECONDS"),
        description="Polling loop interval in seconds for checking due scheduled tasks",
    )
    missed_task_policy: str = Field(
        default="skip",
        validation_alias=AliasChoices("MISSED_TASK_POLICY"),
        description="Policy for overdue tasks missed while offline ('skip' or 'run_once')",
    )
    max_task_execution_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("MAX_TASK_EXECUTION_SECONDS"),
        description="Maximum execution runtime in seconds for a scheduled task before timeout",
    )

    tasks_database_path: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TASKS_DATABASE_PATH"),
        description="Optional custom file path for SQLite task storage (defaults to assistant.db)",
    )

    # Controlled Autonomous Planning Settings (Phase 15)
    planning_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("PLANNING_ENABLED"),
        description="Whether structured multi-step planning is enabled",
    )
    max_plan_steps: int = Field(
        default=20,
        validation_alias=AliasChoices("MAX_PLAN_STEPS"),
        description="Maximum steps allowed per plan",
    )
    max_plan_tool_calls: int = Field(
        default=30,
        validation_alias=AliasChoices("MAX_PLAN_TOOL_CALLS"),
        description="Maximum cumulative tool calls permitted for a single plan",
    )
    max_plan_runtime_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices("MAX_PLAN_RUNTIME_SECONDS"),
        description="Maximum runtime in seconds allowed for a plan execution",
    )
    max_plan_failures: int = Field(
        default=3,
        validation_alias=AliasChoices("MAX_PLAN_FAILURES"),
        description="Maximum permitted step failures before plan termination",
    )
    max_replans: int = Field(
        default=3,
        validation_alias=AliasChoices("MAX_REPLANS"),
        description="Maximum dynamic re-planning iterations permitted per plan",
    )
    max_step_retries: int = Field(
        default=1,
        validation_alias=AliasChoices("MAX_STEP_RETRIES"),
        description="Maximum retries for transient step failures",
    )
    max_identical_step_repetitions: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_IDENTICAL_STEP_REPETITIONS"),
        description="Maximum identical failed step attempts before loop breaker halts execution",
    )
    auto_approve_safe_plans: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTO_APPROVE_SAFE_PLANS"),
        description="Automatically start execution of read-only/informational plans",
    )
    max_plan_context_bytes: int = Field(
        default=8192,
        validation_alias=AliasChoices("MAX_PLAN_CONTEXT_BYTES"),
        description="Maximum size in bytes of formatted history passed to planner",
    )

    # Intelligent Local Model Routing Settings (Phase 16)
    model_routing_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("MODEL_ROUTING_ENABLED"),
        description="Master switch for intelligent local model routing",
    )
    model_routing_mode: str = Field(
        default="auto",
        validation_alias=AliasChoices("MODEL_ROUTING_MODE"),
        description="Routing mode: 'auto', 'fast', 'standard', 'heavy', or specific model name",
    )
    enable_fast_path: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_FAST_PATH"),
        description="Master switch for deterministic fast path bypass (<15ms)",
    )
    fast_model: str = Field(
        default="qwen3:4b",
        validation_alias=AliasChoices("FAST_MODEL"),
        description="Configured fast/lightweight model for simple chat and direct tasks",
    )
    fast_chat_think: bool = Field(
        default=False,
        validation_alias=AliasChoices("FAST_CHAT_THINK"),
        description="Whether thinking tags are enabled for fast conversational turns",
    )
    fast_num_ctx: int = Field(
        default=2048,
        validation_alias=AliasChoices("FAST_NUM_CTX"),
        description="Context token budget for fast conversational turns",
    )
    fast_num_predict: int = Field(
        default=384,
        validation_alias=AliasChoices("FAST_NUM_PREDICT"),
        description="Max token generation limit for fast conversational turns",
    )
    fast_temperature: float = Field(
        default=0.4,
        validation_alias=AliasChoices("FAST_TEMPERATURE"),
        description="Sampling temperature for fast conversational turns",
    )
    fast_keep_alive: str = Field(
        default="30m",
        validation_alias=AliasChoices("FAST_KEEP_ALIVE"),
        description="Residency keep-alive duration for fast conversational model",
    )
    standard_model: str = Field(
        default="qwen3:8b",
        validation_alias=AliasChoices("STANDARD_MODEL"),
        description="Configured standard model for RAG, moderate code, and daily tasks",
    )
    heavy_model: str = Field(
        default="qwen3:30b",
        validation_alias=AliasChoices("HEAVY_MODEL"),
        description="Configured heavyweight model for complex reasoning, planning, and debugging",
    )
    model_fallback_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("MODEL_FALLBACK_ENABLED"),
        description="Whether to automatically fall back to available models if preferred model is uninstalled",
    )
    preload_fast_model: bool = Field(
        default=False,
        validation_alias=AliasChoices("PRELOAD_FAST_MODEL"),
        description="Whether to keep the fast model preloaded/warmed in memory",
    )
    preload_heavy_model: bool = Field(
        default=False,
        validation_alias=AliasChoices("PRELOAD_HEAVY_MODEL"),
        description="Whether to keep the heavy model preloaded (default False for RAM conservation)",
    )
    max_context_bytes_for_fast: int = Field(
        default=4096,
        validation_alias=AliasChoices("MAX_CONTEXT_BYTES_FOR_FAST"),
        description="Maximum prompt context size before routing away from fast model",
    )
    max_context_bytes_for_standard: int = Field(
        default=16384,
        validation_alias=AliasChoices("MAX_CONTEXT_BYTES_FOR_STANDARD"),
        description="Maximum prompt context size before routing to heavy model",
    )

    # Advanced Context & Personalization Settings (Phase 17)
    context_management_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("CONTEXT_MANAGEMENT_ENABLED"),
        description="Master switch for intelligent context management, budgeting, and relevance ranking",
    )
    max_context_tokens: int = Field(
        default=12288,
        validation_alias=AliasChoices("MAX_CONTEXT_TOKENS"),
        description="Global ceiling for total assembled input context tokens",
    )
    max_conversation_context_tokens: int = Field(
        default=4096,
        validation_alias=AliasChoices("MAX_CONVERSATION_CONTEXT_TOKENS"),
        description="Maximum tokens budgeted for conversation history and summaries",
    )
    max_memory_context_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices("MAX_MEMORY_CONTEXT_TOKENS"),
        description="Maximum tokens budgeted for injected relevant persistent memories",
    )
    max_knowledge_context_tokens: int = Field(
        default=2048,
        validation_alias=AliasChoices("MAX_KNOWLEDGE_CONTEXT_TOKENS"),
        description="Maximum tokens budgeted for injected relevant RAG knowledge chunks",
    )
    max_tool_context_tokens: int = Field(
        default=2048,
        validation_alias=AliasChoices("MAX_TOOL_CONTEXT_TOKENS"),
        description="Maximum tokens budgeted for tool output context bounding",
    )
    max_system_context_tokens: int = Field(
        default=512,
        validation_alias=AliasChoices("MAX_SYSTEM_CONTEXT_TOKENS"),
        description="Maximum tokens budgeted for dynamically injected system state metrics",
    )
    response_token_reserve: int = Field(
        default=2048,
        validation_alias=AliasChoices("RESPONSE_TOKEN_RESERVE"),
        description="Tokens reserved strictly for model output generation",
    )
    recent_messages_count: int = Field(
        default=8,
        validation_alias=AliasChoices("RECENT_MESSAGES_COUNT"),
        description="Number of most recent conversation messages preserved verbatim before summarization",
    )
    summarization_threshold_messages: int = Field(
        default=12,
        validation_alias=AliasChoices("SUMMARIZATION_THRESHOLD_MESSAGES"),
        description="Message count threshold triggering conversation history compaction and summarization",
    )
    default_response_style: str = Field(
        default="balanced",
        validation_alias=AliasChoices("DEFAULT_RESPONSE_STYLE", "RESPONSE_STYLE"),
        description="Default assistant response style: 'concise', 'balanced', or 'detailed'",
    )
    context_cache_ttl_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("CONTEXT_CACHE_TTL_SECONDS"),
        description="Time-to-live in seconds for cached context candidates (user profile, project context)",
    )
    auto_system_context_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTO_SYSTEM_CONTEXT_ENABLED"),
        description="Whether to automatically inject hardware/system metrics when relevant to user query",
    )

    # Intelligence & Agent Quality Upgrade Settings (Phase 18)
    autonomy_level: str = Field(
        default="confirm_actions",
        validation_alias=AliasChoices("AUTONOMY_LEVEL"),
        description="User-selected autonomy level ('assisted', 'confirm_actions', 'controlled_autonomous')",
    )
    max_tool_retries: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_TOOL_RETRIES"),
        description="Maximum retry attempts permitted for transient tool failures before halting or asking user",
    )
    quality_checks_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("QUALITY_CHECKS_ENABLED"),
        description="Whether to run deterministic response quality, false-completion, and anti-repetition checks",
    )
    quality_telemetry_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("QUALITY_TELEMETRY_ENABLED"),
        description="Whether to record local interaction quality telemetry in assistant.db",
    )
    strict_goal_verification: bool = Field(
        default=True,
        validation_alias=AliasChoices("STRICT_GOAL_VERIFICATION"),
        description="Whether to physically verify host environment postconditions before concluding goals",
    )
    tool_selection_confidence_threshold: float = Field(
        default=0.65,
        validation_alias=AliasChoices("TOOL_SELECTION_CONFIDENCE_THRESHOLD"),
        description="Minimum confidence score required to automatically execute a selected tool without clarification",
    )
    max_repetition_count: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_REPETITION_COUNT"),
        description="Maximum duplicate tool/argument/result repetitions permitted before breaking loop",
    )

    # Multimodal Vision & Image Understanding Settings (Phase 20)
    vision_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("VISION_ENABLED"),
        description="Whether multimodal image understanding is enabled",
    )
    vision_model: str = Field(
        default="llava:latest",
        validation_alias=AliasChoices("VISION_MODEL"),
        description="Default preferred local vision model tag (e.g. 'llava:latest', 'minicpm-v:latest', 'qwen2.5-vl:latest')",
    )
    allow_screen_capture: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLOW_SCREEN_CAPTURE"),
        description="Whether user permits one-shot desktop screenshot capture (disabled by default for privacy)",
    )
    max_image_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias=AliasChoices("MAX_IMAGE_BYTES"),
        description="Maximum file size in bytes permitted for image input (default 10 MB)",
    )
    max_image_pixels: int = Field(
        default=3840 * 2160,
        validation_alias=AliasChoices("MAX_IMAGE_PIXELS"),
        description="Maximum total pixel count permitted for image input (default ~8.3 MP)",
    )
    max_image_width: int = Field(
        default=3840,
        validation_alias=AliasChoices("MAX_IMAGE_WIDTH"),
        description="Maximum image width in pixels permitted",
    )
    max_image_height: int = Field(
        default=2160,
        validation_alias=AliasChoices("MAX_IMAGE_HEIGHT"),
        description="Maximum image height in pixels permitted",
    )
    max_images_per_request: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_IMAGES_PER_REQUEST"),
        description="Maximum number of images allowed per turn (default 2)",
    )
    image_downscale_max_dim: int = Field(
        default=1280,
        validation_alias=AliasChoices("IMAGE_DOWNSCALE_MAX_DIM"),
        description="Maximum dimension for smooth downscaling before multimodal inference to save RAM/tokens",
    )
    image_cache_ttl_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("IMAGE_CACHE_TTL_SECONDS"),
        description="Time-to-live in seconds for cached processed image artifacts",
    )













    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in valid_levels:
            raise ValueError(f"Invalid log_level '{value}'. Must be one of {valid_levels}")
        return upper

    def resolve_path(self, path: Path) -> Path:
        """Resolve a relative path against the project root if not already absolute."""
        if path.is_absolute():
            return path.resolve()
        return (self.project_root / path).resolve()

    def get_resolved_data_dir(self) -> Path:
        """Return the absolute path for data_dir."""
        return self.resolve_path(self.data_dir)

    def get_resolved_logs_dir(self) -> Path:
        """Return the absolute path for logs_dir."""
        return self.resolve_path(self.logs_dir)

    def get_resolved_allowed_roots(self) -> list[Path]:
        """Return the list of validated absolute paths allowed for file-system access."""
        if self.filesystem_allowed_roots:
            return [self.resolve_path(Path(r)) for r in self.filesystem_allowed_roots]
        # Conservative default: confine filesystem access strictly to the local data directory
        return [self.get_resolved_data_dir()]

    def get_resolved_protected_paths(self) -> list[Path]:
        """Return paths that the assistant must never modify or delete."""
        protected: list[Path] = []
        for p in self.filesystem_protected_paths:
            try:
                protected.append(self.resolve_path(Path(p)))
            except Exception:
                continue

        # Default system protections for Windows/OS directories
        candidates = [
            Path("C:/Windows"),
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
            self.resolve_path(self.project_root / "app"),  # Protect assistant source code
        ]
        for c in candidates:
            if c.exists() and c not in protected:
                protected.append(c.resolve())

        return protected

    def get_log_file_path(self) -> Path:
        """Return the full path to the active log file."""
        return self.get_resolved_logs_dir() / self.log_file_name

    def get_resolved_database_path(self) -> Path:
        """Return the absolute path for the SQLite memory database."""
        if self.memory_database_path:
            return self.resolve_path(Path(self.memory_database_path))
        return self.get_resolved_data_dir() / "assistant.db"

    def get_resolved_knowledge_dir(self) -> Path:
        """Return the absolute path for the knowledge storage directory."""
        if self.knowledge_data_dir:
            return self.resolve_path(Path(self.knowledge_data_dir))
        return self.get_resolved_data_dir() / "knowledge"

    def get_resolved_knowledge_db_path(self) -> Path:
        """Return the absolute path for the SQLite knowledge database."""
        if self.knowledge_database_path:
            return self.resolve_path(Path(self.knowledge_database_path))
        return self.get_resolved_knowledge_dir() / "knowledge.db"

    def get_resolved_tasks_db_path(self) -> Path:
        """Return the absolute path for the SQLite task database."""
        if self.tasks_database_path:
            return self.resolve_path(Path(self.tasks_database_path))
        return self.get_resolved_database_path()

    def ensure_directories(self) -> None:
        """Ensure that data, log, memory, and knowledge directories exist."""
        self.get_resolved_data_dir().mkdir(parents=True, exist_ok=True)
        self.get_resolved_logs_dir().mkdir(parents=True, exist_ok=True)
        self.get_resolved_database_path().parent.mkdir(parents=True, exist_ok=True)
        self.get_resolved_knowledge_dir().mkdir(parents=True, exist_ok=True)
        self.get_resolved_knowledge_db_path().parent.mkdir(parents=True, exist_ok=True)
        self.get_resolved_tasks_db_path().parent.mkdir(parents=True, exist_ok=True)






@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()

