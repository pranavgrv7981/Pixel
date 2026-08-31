"""Data models and capability metadata profiles for local Ollama models."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ModelRole(str, Enum):
    """Conceptual role assigned to a local model."""

    FAST = "fast"
    STANDARD = "standard"
    HEAVY = "heavy"
    VISION = "vision"
    EMBEDDING = "embedding"
    STT = "stt"
    TTS = "tts"


class ModelSizeClass(str, Enum):
    """Size category indicating memory and compute requirements."""

    TINY = "tiny"        # < 2B params (< 2 GB RAM)
    SMALL = "small"      # 2B - 7B params (2 - 6 GB RAM)
    MEDIUM = "medium"    # 7B - 14B params (6 - 12 GB RAM)
    LARGE = "large"      # > 14B params (> 12 GB RAM)


class ReasoningLevel(str, Enum):
    """Reasoning capability level for task matching."""

    BASIC = "basic"          # Simple Q&A, greetings, formatting
    MODERATE = "moderate"    # Single-turn tools, basic code, memory lookup
    ADVANCED = "advanced"    # Multi-tool chaining, RAG synthesis, debugging
    EXPERT = "expert"        # Multi-step planning, complex reasoning, deep C/Python analysis


class ModelCapabilities(BaseModel):
    """Technical features and constraints supported by the model."""

    tool_calling: bool = Field(default=True, description="Supports structured function/tool calling")
    json_mode: bool = Field(default=True, description="Supports structured JSON output")
    reasoning_level: ReasoningLevel = Field(default=ReasoningLevel.MODERATE)
    context_length: int = Field(default=16384, description="Maximum supported context token limit")
    embedding: bool = Field(default=False, description="Supports text embeddings")
    vision: bool = Field(default=False, description="Supports image/multimodal input")


class ModelProfile(BaseModel):
    """Detailed profile characterizing a specific local Ollama model."""

    name: str = Field(..., description="Exact model tag in Ollama (e.g. 'qwen3:30b')")
    size_class: ModelSizeClass = Field(default=ModelSizeClass.MEDIUM)
    role: ModelRole = Field(default=ModelRole.STANDARD)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    preferred_for: list[str] = Field(
        default_factory=list,
        description="List of task types this model is optimized for",
    )
    is_default: bool = Field(default=False, description="Whether this is the fallback default for its role")
    description: Optional[str] = None
    estimated_ram_mb: int = Field(default=4096, description="Estimated RAM consumption in megabytes")
