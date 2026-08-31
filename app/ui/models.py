"""Data models and state definitions for the PySide6 desktop user interface."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of a chat message displayed in the UI."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class UIState(str, Enum):
    """Current operational state of the assistant desktop UI."""
    IDLE = "idle"
    THINKING = "thinking"
    STREAMING = "streaming"
    EXECUTING_TOOL = "executing_tool"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ERROR = "error"


class PixelSummonState(str, Enum):
    """Lifecycle states for summoning and activation of the Pixel assistant."""
    PIXEL_IDLE = "pixel_idle"
    PIXEL_SUMMONING = "pixel_summoning"
    PIXEL_READY = "pixel_ready"


class TurnMetrics(BaseModel):
    """Execution latency and generation performance telemetry for a single assistant turn."""
    ttft: Optional[float] = Field(default=None, description="Time to first token in seconds")
    total_time: float = Field(default=0.0, description="Total generation duration in seconds")
    chunks_count: int = Field(default=0, description="Number of stream chunks received")
    chars_count: int = Field(default=0, description="Total response character length")
    tokens_per_second: float = Field(default=0.0, description="Estimated generation speed (tokens/sec)")
    model_name: str = Field(default="", description="Name of the model that generated the response")
    role: str = Field(default="", description="Model tier/role (e.g. fast, standard, heavy)")
    is_fallback: bool = Field(default=False, description="Whether fallback model routing occurred")


class ToolEvent(BaseModel):
    """Metadata regarding a tool execution event displayed in the chat view."""
    tool_name: str
    risk_level: str
    status: str = "running"  # running, success, denied, failed
    summary: str = ""
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    """Represents a message item rendered in the scrollable chat view."""
    id: str
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_events: list[ToolEvent] = Field(default_factory=list)
    metrics: Optional[TurnMetrics] = None
    is_streaming: bool = False


class ConversationItem(BaseModel):
    """Metadata for a conversation entry displayed in the sidebar."""
    id: str
    title: str
    updated_at: datetime
    message_count: int = 0


class BackendStatus(BaseModel):
    """Real-time diagnostic health status of the backend subsystems."""
    ollama_connected: bool = False
    base_url: str = "http://localhost:11434"
    model_name: str = "qwen3:30b"
    model_available: bool = False
    available_models: list[str] = Field(default_factory=list)
    memory_ready: bool = False
    knowledge_ready: bool = False
    docs_count: int = 0
    browser_active: bool = False
    voice_ready: bool = True
    voice_state: str = "idle"
    voice_wake_enabled: bool = False
    tts_ready: bool = True
    tts_state: str = "idle"
    automation_enabled: bool = True
    active_triggers_count: int = 0
    active_tasks_count: int = 0
    tools_count: int = 58
    security_active: bool = True
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
