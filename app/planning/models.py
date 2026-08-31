"""Data models and schemas for structured planning, step graphs, and execution budgets."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field

from app.tools.base import RiskLevel


class StepStatus(str, Enum):
    """Execution status of an individual plan step."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class PlanStatus(str, Enum):
    """Lifecycle status of a multi-step plan."""

    DRAFT = "draft"
    VALIDATING = "validating"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailureType(str, Enum):
    """Classification of step execution failure."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    SECURITY_DENIED = "security_denied"
    VALIDATION_ERROR = "validation_error"
    USER_DENIED = "user_denied"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class PlanStep(BaseModel):
    """A discrete, executable action step within a plan referencing a registered tool."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order: int = Field(default=1, description="Sequential display order")
    description: str = Field(..., description="Human-readable description of what this step does")
    tool_name: str = Field(..., description="Name of the registered tool to invoke")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Validated arguments for the tool")
    dependencies: list[str] = Field(
        default_factory=list,
        description="List of prerequisite step IDs or step numbers that must succeed before this step can run",
    )
    risk_level: RiskLevel = Field(default=RiskLevel.READ, description="Evaluated risk level of the tool")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Current step state")
    result_summary: Optional[str] = Field(default=None, description="Concise summary of tool execution output")
    error_message: Optional[str] = Field(default=None, description="Error message if step failed")
    failure_type: Optional[FailureType] = Field(default=None, description="Classified failure category")
    retries_used: int = Field(default=0, description="Number of retry attempts executed")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    def is_finished(self) -> bool:
        """True if the step reached a terminal state."""
        return self.status in {
            StepStatus.COMPLETED,
            StepStatus.FAILED,
            StepStatus.SKIPPED,
            StepStatus.BLOCKED,
            StepStatus.CANCELLED,
        }


class PlanBudget(BaseModel):
    """Resource and safety limits bounding plan execution to prevent runaways and infinite loops."""

    max_steps: int = Field(default=20, description="Maximum total steps allowed in plan")
    max_tool_calls: int = Field(default=30, description="Maximum cumulative tool calls permitted")
    max_runtime_seconds: float = Field(default=600.0, description="Maximum execution duration in seconds")
    max_failures: int = Field(default=3, description="Maximum allowed failed steps before halting plan")
    max_replans: int = Field(default=3, description="Maximum dynamic re-planning iterations allowed")

    # Dynamic consumption tracking
    steps_executed: int = Field(default=0)
    tool_calls_used: int = Field(default=0)
    runtime_seconds_used: float = Field(default=0.0)
    failures_count: int = Field(default=0)
    replans_count: int = Field(default=0)

    def is_exhausted(self) -> tuple[bool, Optional[str]]:
        """Check if any execution budget limit has been reached."""
        if self.steps_executed >= self.max_steps:
            return True, f"Step limit reached ({self.steps_executed}/{self.max_steps})"
        if self.tool_calls_used >= self.max_tool_calls:
            return True, f"Tool call limit reached ({self.tool_calls_used}/{self.max_tool_calls})"
        if self.runtime_seconds_used >= self.max_runtime_seconds:
            return True, f"Runtime limit exceeded ({self.runtime_seconds_used:.1f}s/{self.max_runtime_seconds}s)"
        if self.failures_count >= self.max_failures:
            return True, f"Failure limit reached ({self.failures_count}/{self.max_failures})"
        if self.replans_count > self.max_replans:
            return True, f"Re-plan limit exceeded ({self.replans_count}/{self.max_replans})"
        return False, None


class Plan(BaseModel):
    """Complete multi-step execution plan addressing a specific user goal."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = Field(..., description="Original user objective or requested task")
    status: PlanStatus = Field(default=PlanStatus.DRAFT, description="Current lifecycle state")
    steps: list[PlanStep] = Field(default_factory=list, description="Ordered sequence of action steps")
    budget: PlanBudget = Field(default_factory=PlanBudget, description="Execution limits and counters")
    success_criteria: list[str] = Field(
        default_factory=list, description="List of verifiable success conditions"
    )
    is_safe_plan: bool = Field(
        default=True, description="True if all steps are low/read risk and can run without confirmation"
    )
    requires_user_approval: bool = Field(
        default=False, description="Whether plan requires upfront user approval before launching"
    )
    version: int = Field(default=1, description="Plan version incremented on re-planning")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    final_summary: Optional[str] = Field(default=None, description="Final outcome summary of the plan")

    def get_step_by_id(self, step_id: str) -> Optional[PlanStep]:
        """Find a step by its unique ID."""
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def get_step_by_order(self, order: int) -> Optional[PlanStep]:
        """Find a step by its sequential order index."""
        for s in self.steps:
            if s.order == order:
                return s
        return None

    def update_safety_assessment(self) -> None:
        """Evaluate overall plan risk level from its step risks."""
        risky = any(s.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL} for s in self.steps)
        self.is_safe_plan = not risky
        self.requires_user_approval = risky
