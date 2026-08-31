"""Data structures, enums, and models for scheduled tasks and execution logs."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Supported task recurrence and scheduling types."""
    ONE_TIME = "one_time"
    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"


class TaskStatus(str, Enum):
    """Lifecycle status states of a scheduled task."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskActionType(str, Enum):
    """Controlled whitelisted action types that scheduled tasks may execute."""
    ASSISTANT_REMINDER = "assistant_reminder"
    ASSISTANT_INFORMATION_QUERY = "assistant_information_query"
    ASSISTANT_MEMORY_QUERY = "assistant_memory_query"
    ASSISTANT_KNOWLEDGE_QUERY = "assistant_knowledge_query"
    ASSISTANT_MESSAGE = "assistant_message"


class TaskSchedule(BaseModel):
    """Structured schedule definition parameters."""
    interval_seconds: Optional[int] = None
    daily_time_utc: Optional[str] = None  # Format: "HH:MM" in 24h UTC
    weekly_day: Optional[int] = None      # 0=Monday ... 6=Sunday
    weekly_time_utc: Optional[str] = None # Format: "HH:MM" in 24h UTC
    exact_run_at_utc: Optional[datetime] = None


class Task(BaseModel):
    """Persistent task definition."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: Optional[str] = None
    task_type: TaskType
    status: TaskStatus = TaskStatus.ACTIVE
    schedule: TaskSchedule
    action_type: TaskActionType = TaskActionType.ASSISTANT_REMINDER
    action_payload: dict[str, Any] = Field(default_factory=dict)
    timezone: str = "UTC"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    run_count: int = 0
    failure_count: int = 0
    max_runs: Optional[int] = None

    @property
    def is_due(self) -> bool:
        """Check if task is currently due for execution."""
        if self.status != TaskStatus.ACTIVE or self.next_run_at is None:
            return False
        now_utc = datetime.now(timezone.utc)
        return self.next_run_at <= now_utc


class TaskExecution(BaseModel):
    """Historical execution record of a task occurrence."""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    occurrence_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: str = "running"  # "success", "failed", "running"
    result_summary: Optional[str] = None
    error_summary: Optional[str] = None


class TaskExecutionContext(BaseModel):
    """Security execution context passed during scheduled background task execution."""
    task_id: str
    execution_id: str
    trigger_time: datetime
    source: str = "scheduler"
    interactive: bool = False


class TaskSummary(BaseModel):
    """Compact summary of a task for UI listings and tool responses."""
    id: str
    title: str
    task_type: TaskType
    status: TaskStatus
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    run_count: int = 0
    failure_count: int = 0
