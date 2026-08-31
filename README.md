# Local AI Personal Assistant

A fully local, extensible desktop virtual assistant powered by Ollama.

The assistant is designed to operate locally and offline, execute verified actions through a strict permission and safety model, maintain conversational state and persistent memory, and progressively expand into browser automation, voice interaction, RAG over personal documents, and scheduled tasks.

---

## Target Architecture

```text
USER
 │
 ├── Text
 └── Voice
      │
      ▼
┌──────────────────────────────┐
│          Desktop UI          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Assistant Core          │
│                              │
│ Conversation Manager         │
│ Agent / Orchestrator         │
│ Tool Router                  │
│ Memory Manager               │
│ Permission Manager           │
└──────────────┬───────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
    Ollama   Tools    Memory
              │
       ┌──────┼──────────────┐
       ▼      ▼              ▼
     Files  System         Browser
```

---

## Core Design Principles

1. **Ollama is the model provider, not the entire assistant**: The application code strictly manages tool execution, permissions, memory, error handling, state, and orchestration.
2. **Tools are first-class objects**: Tools follow a strict pipeline:
   `LLM Request -> Tool Validation -> Permission Check -> Tool Execution -> Result Verification -> Model Response`.
3. **Safety before powerful tools**: Operations are categorized by risk level (`READ`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`). Arbitrary command execution is never exposed unchecked.
4. **Never trust the LLM's claims**: Tools physically verify results on the host system before reporting outcomes.
5. **Incremental phase-based implementation**: Each phase is independently developed, tested, and verified.

---

## Project Structure

```text
local_assistant/
│
├── app/
│   ├── core/
│   │   ├── config.py         # Pydantic Settings & environment variables
│   │   ├── logging.py        # Centralized console and rotating file logging
│   │   ├── exceptions.py     # Domain exception hierarchy
│   │   └── ollama_client.py  # Isolated Ollama client & typed health layer
│   │
│   ├── agent/                # Multi-turn conversation engine and agent loop
│   │   ├── __init__.py
│   │   ├── agent.py          # Agent orchestrator coordinating model & tool execution
│   │   └── conversation.py   # Message, Conversation, and ConversationManager
│   ├── tools/                # Extensible tool engine and registries
│   │   ├── __init__.py
│   │   ├── base.py           # Tool, ToolResult, RiskLevel abstractions
│   │   ├── registry.py       # ToolRegistry for registration and Ollama schema generation
│   │   ├── demo.py           # Harmless demo tools (get_current_time, calculate)
│   │   ├── path_guard.py     # Central path validation and boundary defense layer (Phase 5)
│   │   ├── filesystem.py     # Controlled local filesystem tools (Phase 5)
│   │   ├── system.py         # Hardware, OS, and process inspection tools (Phase 6)
│   │   └── applications.py   # Whitelisted application management tools (Phase 6)
│   ├── security/             # Guardrails, risk policy, and permission system (Phase 4)
│   │   ├── __init__.py
│   │   ├── permissions.py    # PermissionDecision, ExecutionContext, SecurityDecision
│   │   ├── policies.py       # SecurityPolicy and risk matrix evaluation
│   │   ├── confirmations.py  # ConfirmationProvider, CLI & Non-interactive providers
│   │   ├── audit.py          # Structured audit logging and credential scrubbing
│   │   └── manager.py        # Central PermissionManager orchestrator
│   ├── memory/               # Context and persistent storage (Phase 8)
│   ├── voice/                # Audio I/O interfaces (Phases 11-12)
│   ├── browser/              # Web navigation utilities (Phase 10)
│   └── ui/                   # Desktop graphical interface (Phase 13)
│
├── tests/                    # Unit and integration test suite
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_logging.py
│   ├── test_exceptions.py
│   ├── test_ollama_client.py
│   ├── test_ollama_status.py
│   ├── test_conversation.py
│   ├── test_tools.py
│   ├── test_tool_registry.py
│   ├── test_agent.py
│   ├── test_permissions.py
│   ├── test_confirmations.py
│   ├── test_audit.py
│   ├── test_security_integration.py
│   ├── test_filesystem_security.py
│   ├── test_filesystem_tools.py
│   ├── test_filesystem_integration.py
│   ├── test_system_tools.py
│   ├── test_application_tools.py
│   ├── test_system_integration.py
│   └── test_main.py
│
├── data/                     # Persistent local application storage
├── logs/                     # Application logs (assistant.log)
├── main.py                   # Application entry point
├── requirements.txt          # Active phase dependencies
├── .env.example              # Environment variables template
├── .gitignore                # Git exclusions
└── README.md
```

---

## Current Status: Phase 11 Completed

- **Phase 0: Project Architecture and Foundation** (Completed).
- **Phase 1: Ollama Local Model Integration** (Completed).
- **Phase 2: Conversation Engine** (Completed).
- **Phase 3: Tool Calling Architecture** (Completed).
- **Phase 4: Permission and Safety System** (Completed).
- **Phase 5: File-System Tools** (Completed).
- **Phase 6: System and Application Tools** (Completed).
- **Phase 7: Controlled Terminal and Code Execution** (Completed).
- **Phase 8: Persistent Memory** (Completed).
- **Phase 9: Personal Knowledge / RAG** (Completed).
- **Phase 10: Browser Automation** (Completed).
- **Phase 11: Dedicated Desktop Application** (Completed).
- 49 tools registered and governed by `ToolRegistry` and `PermissionManager`:
  - Demo tools (3): `get_current_time`, `calculate`, `demo_medium_risk_tool`.
  - Filesystem tools (12): `list_directory`, `get_file_info`, `search_files`, `read_text_file`, `create_directory`, `create_file`, `write_text_file`, `copy_file`, `move_file`, `rename_file`, `delete_file`, `delete_directory`.
  - System info tools (7): `get_system_info`, `get_cpu_usage`, `get_memory_usage`, `get_battery_status`, `get_uptime`, `list_running_processes`, `get_process_info`.
  - Application tools (3): `open_application`, `close_application`, `is_application_running`.
  - Controlled terminal tools (6): `git_status`, `git_diff`, `compile_c_program`, `run_python_file`, `run_pytest`, `run_c_program`.
  - Persistent memory tools (3): `remember_memory`, `recall_memory`, `forget_memory`.
  - Personal knowledge / RAG tools (5): `search_knowledge`, `list_indexed_documents`, `index_document`, `index_directory`, `remove_document`.
  - Browser automation tools (10): `browser_open`, `browser_search`, `browser_get_page`, `browser_current_page`, `browser_click`, `browser_type`, `browser_scroll`, `browser_back`, `browser_forward`, `browser_close`.
- Dedicated PySide6 Desktop GUI:
  - Launch via `python main.py --gui` or `python -m app.ui`.
  - Asynchronous background worker (`QThread`) with token streaming and tool event signals.
  - Interactive modal security confirmations (`GuiConfirmationProvider`) for `MEDIUM` and `HIGH` risk actions.
  - Persistent conversation management sidebar, multiline input with Shift+Enter, status bar with live Ollama model dropdown, memory viewer dialog, RAG document indexer dialog, and settings dialog.
- 346 automated unit and integration tests passing.



---

## Getting Started

### Prerequisites

* Python 3.12+ (tested on Python 3.14)
* Ollama installed and running locally (`http://localhost:11434`)
* PowerShell or bash

### Installation

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Configure environment:

```powershell
cp .env.example .env
```

---

## Running the Application

Launch the assistant:

```powershell
python main.py
```

Run system, Ollama, tool registry, and security policy diagnostics:

```powershell
python main.py --check
```

Start an interactive multi-turn conversation session:

```powershell
python main.py --interactive
```

Send a single-turn chat prompt:

```powershell
python main.py --chat "What is my current RAM usage?" --model qwen3:30b
```

---

## Running Tests

Run the full mocked test suite with pytest:

```powershell
pytest -v
```

---

## Desktop Application & Voice Input (Phases 11-12)

Launch the dedicated PySide6 desktop GUI with local speech-to-text:

```powershell
python main.py --gui --model qwen3:30b
```

### Voice Input Architecture & Privacy

```text
User clicks 🎤
       │
       ▼
Audio Capture (sounddevice, 16 kHz 16-bit PCM)
       │
       ▼
Local Transcription (faster-whisper on CPU)
       │
       ▼
Transcribed Text in Input Bar (User can edit/review)
       │
       ▼
User clicks Send ──► Existing Assistant Pipeline
```

- **100% Local & Offline**: Transcription runs entirely on local CPU via `faster-whisper`. No audio or text is ever transmitted over the network or sent to cloud services.
- **Review Before Send**: The transcript is placed directly into the input text box for the user to review, edit, or delete. It is **never** sent automatically to the agent.
- **Secure Temporary Audio**: Recordings are written to temporary WAV files and strictly deleted immediately after transcription on both success and failure.
- **Microphone Management**: Automatically detects default OS input devices and allows manual selection in Settings.

---

### Phase 13: Local Text-to-Speech (TTS)

```text
Assistant Response (Markdown / Text)
       │
       ▼
Text Sanitizer (Strips markdown fences, code, HTML, and internal markers)
       │
       ▼
TTSController (State: SYNTHESIZING / SPEAKING, Speech Queue)
       │
       ▼ (dispatches to background QThread worker)
TTSWorker ──► Pyttsx3Provider / Windows SAPI5
       │
       ▼ (streams audio through selected playback device)
Audio Output (Speakers / Headphones)
       │
       ▼ (emits speech_finished signal & deletes temporary audio)
TTSController (State: IDLE)
```

- **100% Local & Offline**: Synthesis utilizes native local SAPI5 voices (e.g. *Microsoft David*, *Microsoft Zira*) without cloud dependencies.
- **Speech Text Sanitization**: Markdown code fences (` ``` `), HTML tags, URLs, and asterisks are stripped or converted to pleasant natural phrases before speech generation, while keeping the visual chat bubble text unchanged.
- **User Control & Auto-Speak**: Manual `🔊 Speak` buttons are available on each assistant response. `AUTO_SPEAK_RESPONSES` is **disabled by default** and can be toggled in Settings.
- **Global Stop & Speech Queue**: Seamless utterance queue prevents overlapping playback. Speech can be interrupted anytime with `Ctrl+.` or the stop control.
- **Secure Audio Lifecycle**: Temporary WAV files are strictly deleted in `finally:` blocks immediately after playback.

---

---

### Phase 14: Background Resident Assistant & Real-Time Event Automation

The assistant operates as a **background resident desktop companion** living in the Windows system tray and reacting safely to real-time events and scheduled tasks without continuous LLM polling.

```text
                       APPLICATION
                           │
             ┌─────────────┴──────────────┐
             │                            │
        Desktop UI                  Background Core
             │                            │
             │                     ┌──────┴──────┐
             │                     │ Event Engine│
             │                     └──────┬──────┘
             │                            │
             │               ┌────────────┼─────────────┐
             │               ▼            ▼             ▼
             │          Scheduler     File Watcher   System Monitor
             │               │            │             │
             └───────────────┴────────────┼─────────────┘
                                         ▼
                                  Deterministic Filters
                               (Cooldown, Debounce, Origin)
                                         ▼
                                   Matched Trigger
                                         ▼
                                       Agent
                               (Safe Whitelisted Tools)
                                         ▼
                                Notification / Tray / TTS
```

- **System Tray Residency**: Operates visibly with live status indicator (🟢 Active / ⏸ Paused). Supports instant launching in background via `LocalAssistant.exe --background` or `python main.py --background`.
- **Single-Instance Protection**: Named mutex/socket mechanism guarantees only one assistant instance runs at a time, bringing the active GUI window to focus when launched again.
- **Automated Ollama Lifecycle**: Discovers existing Ollama server or starts it seamlessly in the background without opening console windows. Reuses server if already active to prevent port collisions (`http://localhost:11434`).
- **External Model Storage**: Never bundles or duplicates the 18 GB `qwen3:30b` model within the executable. Respects user-configured `E:\OllamaModels` / `OLLAMA_MODELS`.
- **Master Automation Switch**: Toggleable master switch enables immediate pausing of all background event triggers while retaining interactive chat and voice capabilities.
- **Zero Continuous LLM Polling**: File changes, OS metric thresholds (RAM, CPU, Battery), and application lifecycles are monitored deterministically with low CPU/RAM footprint. Ollama is **only** invoked when an event condition requires language reasoning.
- **Deterministic Filters & Debouncing**: Coalesces rapid filesystem events (500ms debounce window), enforces rate limits (20 events/sec), and prevents cascade loops.
- **Scheduled Tasks & Reminders**: Supports `ONE_TIME`, `INTERVAL`, `DAILY`, and `WEEKLY` schedules with missed-task recovery policies.
- **Fail-Closed Autonomous Security**: Background executions run non-interactively (`interactive=False`). Confirmation-gated dangerous tools (deletion, code execution, browser submissions) fail-closed (`DENY`) and cannot run unattended.
- **Reversible Windows Startup**: User-level registry startup (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) without requiring administrative permissions.

> [!NOTE]
> **Privacy & Resource Disclosure**:
> - The assistant runs visibly in the Windows system tray.
> - It does not secretly monitor keystrokes, microphone, webcam, or screen.
> - The assistant does not continuously invoke the LLM in the background.
> - Background reasoning occurs only when configured events require it.

---

## Production Packaging

The application is packaged as a standalone Windows executable using PyInstaller:

```powershell
# Build executable distribution into dist/LocalAssistant
.venv\Scripts\python.exe -m PyInstaller build/local_assistant.spec --noconfirm

# Run packaged executable
dist\LocalAssistant\LocalAssistant.exe --check --model qwen3:30b
```

---

## Roadmap

- [x] **Phase 0**: Project architecture and foundation
- [x] **Phase 1**: Ollama integration
- [x] **Phase 2**: Conversation engine
- [x] **Phase 3**: Tool-calling architecture
- [x] **Phase 4**: Permission and safety system
- [x] **Phase 5**: File-system tools
- [x] **Phase 6**: System/application tools
- [x] **Phase 7**: Controlled terminal/code tools
- [x] **Phase 8**: Persistent memory
- [x] **Phase 9**: RAG/personal document knowledge
- [x] **Phase 10**: Browser automation
- [x] **Phase 11**: Dedicated desktop application (PySide6)
- [x] **Phase 12**: Local voice input / Speech-to-text
- [x] **Phase 13**: Local text-to-speech
- [x] **Phase 14**: Production Windows App + Auto-Starting Ollama + Resident Real-Time Assistant
- [x] **Phase 15**: Controlled Autonomous Planning
- [x] **Phase 16**: Dynamic Multi-Model Routing & Resource-Aware Orchestration
- [x] **Phase 17**: Advanced Context, Personalization & Context Management
- [x] **Phase 18**: Intelligence & Agent Quality Upgrade
- [x] **Phase 19**: Security Hardening, Reliability & Production Safety
- [x] **Phase 20**: Multi-Modal Vision & Image Understanding
- [ ] **Phase 21**: Voice/Visual Proactive Interaction & Advanced Multimodal Workflows

---

## Phase 17 — Advanced Context, Personalization & Context Management

Phase 17 introduces a centralized context orchestration layer (`app/context/`) ensuring the model receives precisely tailored, budget-bounded, and injection-defended context for every turn:

- **Context Manager Orchestration**: Gathers candidates across 12 context sources, ranks relevance dynamically, calculates model-aware token budgets, and formats structured prompts.
- **Model-Aware Budgeting**: Allocates token budgets proportional to model capacity, reserving 2,048 tokens for response generation and enforcing strict source-level caps (Conversation: 4,096, Memory: 1,536, Knowledge: 2,048, Tools: 1,536, System: 512).
- **Personalization & Response Styles**: Persistent user profile database supporting `CONCISE`, `BALANCED`, and `DETAILED` response styles, technical depth levels, and custom instructions.
- **Active Project Context**: Tracks project metadata and roots, seamlessly integrating with `PathGuard` workspace boundaries.
- **Conversation Compaction & Summaries**: Automatically compacts older conversation turns into structured topic/decision summaries when exceeding message thresholds.
- **Strict Trust Hierarchy & Injection Defense**: Untrusted external documents (RAG) and browser content are quarantined in explicit reference blocks and prevented from masquerading as system or security directives.
- **Context Diagnostics & Inspector UI**: Real-time context inspection dialog in the desktop GUI showing token utilization, source breakdown, and latency metrics.

---

## Phase 18 — Intelligence & Agent Quality Upgrade

Phase 18 elevates the assistant from a simple LLM wrapper to an autonomous, intelligent decision pipeline:

- **Explicit Decision Pipeline**: Replaces simple `prompt -> llm` invocation with a typed state machine: `UNDERSTANDING -> DECISION -> CONTEXT -> MODEL -> EXECUTION -> VERIFICATION -> RECOVERY -> QUALITY_CHECK -> RESPONSE`.
- **Intent Understanding & Action Gating (`IntentAnalyzer`)**: Distinguishes direct answers, tool actions, multi-step plans, and necessary single-question clarifications. Enforces strict "Don't use tools" rules for conceptual and conversational inquiries.
- **Capability-Aware Tool Selection (`CapabilityToolSelector`)**: Dynamically matches intent categories and entities to compact tool subsets, bypassing tools for direct answers and preventing tool hallucinations. Pre-validates argument plausibility before execution.
- **Host Action Verification (`ActionVerifier`)**: Physically inspects real host-system postconditions (files on disk, running processes in process table, compiler output binaries, pytest exit codes) to distinguish tool execution success from high-level goal satisfaction.
- **Failure Classification & Loop Prevention (`FailureRecoveryManager`)**: Classifies failures into typed categories (`NOT_FOUND`, `INVALID_INPUT`, `SECURITY`, `TIMEOUT`, `TRANSIENT`, `ENVIRONMENT`, `LOGICAL`). Uses MD5 fingerprinting to immediately halt duplicate retry loops and enforces zero retries on security denials.
- **Response Quality & False Completion Protection (`ResponseQualityEvaluator`)**: Deterministically prevents false completion claims (e.g. claiming "Done" when actions failed), strips raw JSON dumps into clean markdown, and deduplicates looping phrases.
- **Configurable Autonomy Levels**: Supports `ASSISTED`, `CONFIRM_ACTIONS`, and `CONTROLLED_AUTONOMOUS` modes while maintaining fail-closed security invariants.
- **Agent Quality Telemetry (`AgentQualityTracker`)**: Persists local interaction metrics (goal completion rate, tool selection accuracy, retry counts, latency) in SQLite (`assistant.db`) without logging sensitive user prompts.

---

## Phase 19 — Security Hardening, Reliability & Production Safety

Phase 19 delivers a comprehensive defensive audit and production reliability hardening pass:

- **Security Hierarchy Invariant**: The LLM is NEVER a security authority. Enforces `System -> Security Policy -> Application Policy -> PermissionManager -> PathGuard / ExecutionPolicy -> ToolRegistry -> LLM`.
- **Instruction / Data Quarantine**: Enforces reference data delimiters around RAG documents, browser pages, tool results, and persistent memories to prevent untrusted content from masquerading as system directives.
- **Automated Secret Redaction**: Built-in `RedactingFormatter` and string scrubbers automatically sanitize API keys (`sk-...`, `ghp_...`), passwords, OAuth tokens (`Bearer ...`), and auth credentials from console logs, rotating log files, and audit trails.
- **Database Backup & Integrity Recovery (`DatabaseBackupManager`)**: Automated local SQLite snapshots, `PRAGMA integrity_check` verification, bounded backup rotation, and safe rollback for `assistant.db` and `knowledge.db`.
- **Filesystem Boundary Hardening (`PathGuard`)**: Added explicit rejection for Windows UNC device namespaces (`\\.\`, `\\?\`), null-byte string truncations (`\0`), Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`), and root directory deletions.
- **Code Execution Containment (`ExecutionPolicy`)**: Strictly maintains `shell=False` for all subprocess invocations, blocks forbidden script engines (`powershell`, `cmd`, `bash`, `mshta`), and enforces output truncation and execution timeouts.
- **System Prompt Protection**: Deterministic evaluator interception prevents internal system prompts, hidden instructions, and security policy internals from being leaked via conversational prompts.
- **Adversarial Red-Team & Reliability Suites (`tests/security/`, `tests/reliability/`)**: 26 dedicated adversarial tests validating prompt injection defense, risk spoofing resistance, path traversal, shell injection prevention, planner security denial guards, and database lock recovery.

---

## Phase 20 — Multimodal Vision & Image Understanding

Phase 20 introduces local image and visual understanding with memory bounding, zero automatic downloads, and strict untrusted reference data isolation:

- **Dedicated Vision Package (`app/vision/`)**: Typed data models (`ImageInput`, `VisionResult`, `VisionStatus`), input loaders, format validators, base64 transformers, and `VisionManager`.
- **Image Input Validation & Bounding**: Supports PNG, JPEG, WEBP, and BMP formats with strict byte size (`MAX_IMAGE_BYTES`), pixel count (`MAX_IMAGE_PIXELS`), and dimension limits. Automatically downscales oversized images smoothly to save RAM and context tokens.
- **No Automatic Model Downloads**: Verified local models first (`qwen3:30b` text-only installed). Cleanly reports `"Vision: Unavailable (No vision-capable local model installed)"` without downloading or failing the application.
- **Model Routing Integration**: `ModelRouter` recognizes `has_images=True` and targets verified multimodal models (`llava`, `minicpm-v`, `qwen2.5-vl`, `llama3.2-vision`) with on-demand memory management.
- **Screenshot & Clipboard Loaders**: One-shot desktop capture protected by explicit `ALLOW_SCREEN_CAPTURE` permission policy. Clipboard buffer loading without automatic polling.
- **Visual Prompt Injection Defense**: Visual text and OCR extracts are classified under `TrustLevel.IMAGE` and isolated within `[REFERENCE DATA (IMAGE)]` quarantine headers, preventing image contents from overriding safety or executing unauthorized tools.
- **Desktop UI Controls**: `InputBar` features `[📎 Attach Image]` and `[📷 Screenshot]` buttons with an interactive thumbnail strip showing dimensions, file size, and removal controls.


