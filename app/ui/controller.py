"""Application Controller coordinating UI interactions, workers, and backend services."""

from typing import Any, Optional
from PySide6.QtCore import QObject, Signal, QTimer

from app.agent.agent import Agent
from app.agent.conversation import Conversation, ConversationManager
from app.browser import BrowserManager
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.knowledge import KnowledgeManager
from app.memory import MemoryManager
from app.security.manager import PermissionManager
from app.ui.confirmation import GuiConfirmationProvider
from app.ui.models import BackendStatus, ConversationItem, UIState
from app.ui.worker import AgentWorker

logger = get_logger("ui.controller")


class AssistantController(QObject):
    """Coordinates UI state transitions, conversation loading, and asynchronous agent execution."""

    # UI State & Chat Signals
    state_changed = Signal(str)
    chunk_received = Signal(str)
    turn_metrics_ready = Signal(object)
    tool_activity_started = Signal(str, dict)
    tool_activity_finished = Signal(str, bool, str)
    turn_completed = Signal(str)
    turn_error = Signal(str)

    # Conversation Management Signals
    conversation_list_updated = Signal(list)
    active_conversation_changed = Signal(str, str, list)

    # Backend Diagnostic Signals
    backend_status_updated = Signal(object)

    def __init__(
        self,
        agent: Agent,
        conversation_manager: ConversationManager,
        memory_manager: MemoryManager,
        knowledge_manager: KnowledgeManager,
        browser_manager: BrowserManager,
        permission_manager: PermissionManager,
        gui_confirmation: GuiConfirmationProvider,
        voice_manager: Optional[Any] = None,
        tts_manager: Optional[Any] = None,
        task_manager: Optional[Any] = None,
        event_engine: Optional[Any] = None,
        context_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.agent = agent
        self.conversation_manager = conversation_manager
        self.memory_manager = memory_manager
        self.knowledge_manager = knowledge_manager
        self.browser_manager = browser_manager
        self.permission_manager = permission_manager
        self.gui_confirmation = gui_confirmation
        self.voice_manager = voice_manager
        self.tts_manager = tts_manager
        self.task_manager = task_manager
        self.event_engine = event_engine
        self.context_manager = context_manager
        self.settings = settings or get_settings()




        self._active_worker: Optional[AgentWorker] = None
        self._current_state = UIState.IDLE
        self._selected_model: str = self.agent.client.default_model

    @property
    def current_state(self) -> UIState:
        return self._current_state

    @property
    def selected_model(self) -> str:
        return self._selected_model

    def set_selected_model(self, model_name: str) -> None:
        """Update active inference model."""
        if model_name:
            self._selected_model = model_name
            self.agent.client.default_model = model_name
            logger.info("Selected model updated to '%s'", model_name)

    def set_state(self, state: UIState) -> None:
        """Transition UI state and notify listeners."""
        self._current_state = state
        self.state_changed.emit(state.value)

    def send_message(self, prompt: str, images: Optional[list[Any]] = None) -> bool:
        """Initiate asynchronous processing of user message."""
        if self._current_state not in (UIState.IDLE, UIState.ERROR):
            logger.warning("Cannot send message while in active state '%s'", self._current_state.value)
            return False

        if not prompt or not prompt.strip():
            return False

        self.set_state(UIState.THINKING)

        worker = AgentWorker(
            agent=self.agent,
            prompt=prompt.strip(),
            model=self._selected_model,
            images=images,
        )
        self._active_worker = worker

        worker.chunk_received.connect(self._on_chunk)
        worker.tool_started.connect(self._on_tool_start)
        worker.tool_finished.connect(self._on_tool_finish)
        worker.metrics_ready.connect(self._on_metrics_ready)
        worker.finished.connect(self._on_worker_finished)
        worker.error_occurred.connect(self._on_worker_error)

        worker.start()
        return True

    def cancel_turn(self) -> None:
        """Cancel ongoing model generation or worker process."""
        if self._active_worker and self._active_worker.isRunning():
            logger.info("Cancelling active worker turn.")
            self._active_worker.cancel()
            self.set_state(UIState.IDLE)

    def _on_chunk(self, chunk: str) -> None:
        if self._current_state != UIState.STREAMING:
            self.set_state(UIState.STREAMING)
        self.chunk_received.emit(chunk)

    def _on_tool_start(self, tool_name: str, args: dict[str, Any]) -> None:
        self.set_state(UIState.EXECUTING_TOOL)
        self.tool_activity_started.emit(tool_name, args)

    def _on_tool_finish(self, tool_name: str, success: bool, summary: str) -> None:
        self.tool_activity_finished.emit(tool_name, success, summary)
        # Return to thinking/streaming state
        self.set_state(UIState.THINKING)

    def _on_metrics_ready(self, metrics: Any) -> None:
        self.turn_metrics_ready.emit(metrics)

    def _on_worker_finished(self, full_response: str) -> None:
        self.set_state(UIState.IDLE)
        self._active_worker = None
        self.turn_completed.emit(full_response)
        self.refresh_conversation_list()

    def _on_worker_error(self, error_message: str) -> None:
        self.set_state(UIState.ERROR)
        self._active_worker = None
        self.turn_error.emit(error_message)

    def new_conversation(self) -> None:
        """Create a fresh conversation session and activate it."""
        conv = self.conversation_manager.create_conversation()
        self.agent.conversation = conv
        self.active_conversation_changed.emit(conv.id, getattr(conv, "title", "New Chat"), conv.messages)
        self.refresh_conversation_list()

    def switch_conversation(self, conversation_id: str) -> None:
        """Switch to an existing conversation by ID."""
        try:
            conv = self.conversation_manager.load_conversation(conversation_id)
            self.agent.conversation = conv
            self.active_conversation_changed.emit(conv.id, getattr(conv, "title", "Conversation"), conv.messages)
        except Exception as err:
            logger.error("Failed to switch to conversation '%s': %s", conversation_id, err)
            self.turn_error.emit(f"Could not load conversation: {err}")

    def refresh_conversation_list(self) -> None:
        """Query persistent conversation store and broadcast list update."""
        try:
            summaries = self.conversation_manager.list_conversations()
            items = []
            for s in summaries:
                raw_mc = getattr(s, "message_count", 0)
                mc = raw_mc() if callable(raw_mc) else (raw_mc or 0)
                items.append(
                    ConversationItem(
                        id=s.id,
                        title=getattr(s, "title", "Conversation"),
                        updated_at=getattr(s, "updated_at", s.created_at),
                        message_count=int(mc),
                    )
                )
            self.conversation_list_updated.emit(items)
        except Exception as err:
            logger.warning("Could not refresh conversation list: %s", err)

    def check_backend_status(self) -> BackendStatus:
        """Poll backend subsystem diagnostic states."""
        client_status = self.agent.client.get_status()
        docs = []
        try:
            docs = self.knowledge_manager.list_documents()
        except Exception:
            pass

        browser_info = self.browser_manager.get_session_info()
        is_browser_active = browser_info.is_active if browser_info else False

        voice_ready = True
        voice_state = "idle"
        if self.voice_manager:
            try:
                v_stat = self.voice_manager.get_status()
                voice_ready = v_stat.is_available
                voice_state = v_stat.state.value
            except Exception:
                pass

        tts_ready = True
        tts_state = "idle"
        if self.tts_manager:
            try:
                t_stat = self.tts_manager.get_status()
                tts_ready = t_stat.is_available
                tts_state = t_stat.state.value
            except Exception:
                pass

        is_auto = self.event_engine.automation_enabled if self.event_engine else True

        cpu_p = 0.0
        ram_p = 0.0
        try:
            import psutil
            cpu_p = psutil.cpu_percent(interval=None)
            ram_p = psutil.virtual_memory().percent
        except Exception:
            pass

        status = BackendStatus(
            ollama_connected=client_status.is_connected,
            base_url=client_status.base_url,
            model_name=self._selected_model,
            model_available=client_status.is_model_available,
            available_models=client_status.available_models,
            memory_ready=True,
            knowledge_ready=True,
            docs_count=len(docs),
            browser_active=is_browser_active,
            voice_ready=voice_ready,
            voice_state=voice_state,
            tts_ready=tts_ready,
            tts_state=tts_state,
            automation_enabled=is_auto,
            tools_count=len(self.agent.registry.list()),
            security_active=True,
            cpu_percent=cpu_p,
            ram_percent=ram_p,
        )
        self.backend_status_updated.emit(status)
        return status

    def shutdown(self) -> None:
        """Cleanly terminate workers, browser sessions, and release resources on UI close."""
        logger.info("AssistantController shutting down...")
        self.cancel_turn()
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.wait(3000)
        try:
            self.browser_manager.close_session()
        except Exception as err:
            logger.warning("Error closing browser session on shutdown: %s", err)
        if self.voice_manager:
            try:
                self.voice_manager.shutdown()
            except Exception as err:
                logger.warning("Error shutting down VoiceManager: %s", err)
        if self.tts_manager:
            try:
                self.tts_manager.shutdown()
            except Exception as err:
                logger.warning("Error shutting down TTSManager: %s", err)
        if self.event_engine:
            try:
                self.event_engine.stop()
            except Exception as err:
                logger.warning("Error stopping EventEngine on shutdown: %s", err)
        if self.task_manager:
            try:
                self.task_manager.shutdown()
            except Exception as err:
                logger.warning("Error stopping TaskManager on shutdown: %s", err)



