"""Domain models, state enums, and structured telemetry records for Phase 18 Agent Intelligence."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class AgentState(str, Enum):
    """Explicit lifecycle states for the AI decision pipeline."""

    UNDERSTANDING = "understanding"
    DIRECT_ANSWER = "direct_answer"
    TOOL_SELECTION = "tool_selection"
    PLAN_SELECTION = "plan_selection"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    RECOVERY = "recovery"
    RESPONSE_EVALUATION = "response_evaluation"
    FINAL_RESPONSE = "final_response"


class ActionType(str, Enum):
    """Primary action routing decision for an incoming user request."""

    ANSWER = "answer"                # Direct conversational / educational response (no tools)
    TOOL = "tool"                    # Single or focused multi-tool execution
    PLAN = "plan"                    # Multi-step autonomous plan
    CLARIFICATION = "clarification"  # Request is ambiguous or missing critical parameters


class FailureCategory(str, Enum):
    """Structured taxonomy for tool and agent execution failures."""

    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    ENVIRONMENT = "environment"
    LOGICAL = "logical"
    SECURITY = "security"


class AutonomyLevel(str, Enum):
    """Configurable user autonomy operating modes."""

    ASSISTED = "assisted"                            # Inspects & answers; confirms before state-modifying actions
    CONFIRM_ACTIONS = "confirm_actions"              # Automatic read/low-risk, explicit confirmation for medium/high-risk
    CONTROLLED_AUTONOMOUS = "controlled_autonomous"  # Pre-approved bounded workflows execute under strict budgets


class RequestIntent(BaseModel):
    """Deep structural interpretation of a user prompt."""

    raw_prompt: str = Field(description="Original user prompt")
    normalized_goal: str = Field(description="Normalized core goal extracted from prompt")
    action_type: ActionType = Field(default=ActionType.ANSWER, description="Determined action path")
    category: str = Field(default="simple_chat", description="Intent category")
    entities: dict[str, Any] = Field(default_factory=dict, description="Extracted parameters (e.g. paths, apps, targets)")
    constraints: list[str] = Field(default_factory=list, description="User constraints and negatives")
    ambiguity_score: float = Field(default=0.0, description="Ambiguity level from 0.0 (exact) to 1.0 (unclear)")
    clarification_prompt: Optional[str] = Field(default=None, description="Targeted question if clarification needed")
    confidence: float = Field(default=1.0, description="Classification confidence")
    requires_tools: bool = Field(default=False, description="Whether tools are needed")
    requires_planning: bool = Field(default=False, description="Whether multi-step planning is required")
    requires_memory: bool = Field(default=False, description="Whether persistent memory lookup is indicated")
    requires_knowledge: bool = Field(default=False, description="Whether RAG knowledge retrieval is indicated")
    suggested_tool_groups: list[str] = Field(default_factory=list, description="Suggested tool capabilities")


class ToolSelectionDecision(BaseModel):
    """Capability-aware tool selection output."""

    selected_tools: list[str] = Field(default_factory=list, description="List of tool names selected for request")
    confidence: float = Field(default=1.0, description="Selection confidence")
    reason: str = Field(default="", description="Reasoning for selection")
    bypassed_tools: list[str] = Field(default_factory=list, description="Tools explicitly excluded to prevent noise")
    pre_validated_arguments: dict[str, Any] = Field(default_factory=dict, description="Validated argument overrides")


class ExecutionVerification(BaseModel):
    """Post-execution validation of host environment state."""

    verified: bool = Field(default=True, description="True if physical postcondition matches expectation")
    goal_achieved: bool = Field(default=True, description="True if user's high-level goal succeeded")
    details: str = Field(default="", description="Human-readable verification summary")
    discrepancies: list[str] = Field(default_factory=list, description="Detected discrepancies between expected and actual state")


class FailureAssessment(BaseModel):
    """Diagnostic assessment and recovery recommendation for a failed action."""

    category: FailureCategory = Field(description="Classified failure category")
    is_retryable: bool = Field(default=False, description="Whether automated retry is permissible")
    safe_alternative: Optional[str] = Field(default=None, description="Suggested safe alternative tool or approach")
    explanation: str = Field(description="User-friendly explanation of why the action failed")


class QualityEvaluation(BaseModel):
    """Deterministic evaluation of final assistant response."""

    passed: bool = Field(default=True, description="True if response passes all quality checks")
    issues: list[str] = Field(default_factory=list, description="Identified quality issues")
    sanitized_content: Optional[str] = Field(default=None, description="Adjusted or cleaned response content")
    false_completion_detected: bool = Field(default=False, description="True if model falsely claimed success")
    quality_score: float = Field(default=1.0, description="Overall quality score from 0.0 to 1.0")


class AgentTelemetryRecord(BaseModel):
    """Local SQLite interaction metrics for agent quality monitoring."""

    interaction_id: str = Field(description="Unique UUID for this interaction")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp")
    intent_category: str = Field(description="Categorized intent")
    action_type: str = Field(description="Action type: answer, tool, plan, clarification")
    model_name: str = Field(description="Selected LLM model")
    tool_count: int = Field(default=0, description="Number of tool calls executed")
    retries_count: int = Field(default=0, description="Number of retries attempted")
    success: bool = Field(default=True, description="True if interaction completed without unhandled failure")
    goal_achieved: bool = Field(default=True, description="True if verified goal succeeded")
    latency_seconds: float = Field(default=0.0, description="Total execution latency in seconds")
    false_completion_prevented: bool = Field(default=False, description="True if false completion claim was intercepted")
