"""Unit tests for ModelProfile and ModelCapabilities definitions."""

import pytest
from app.models.profiles import (
    ModelCapabilities,
    ModelProfile,
    ModelRole,
    ModelSizeClass,
    ReasoningLevel,
)


def test_valid_model_profile_creation() -> None:
    prof = ModelProfile(
        name="qwen3:30b",
        size_class=ModelSizeClass.LARGE,
        role=ModelRole.HEAVY,
        capabilities=ModelCapabilities(
            tool_calling=True,
            json_mode=True,
            reasoning_level=ReasoningLevel.EXPERT,
            context_length=16384,
        ),
        preferred_for=["planning", "reasoning"],
        estimated_ram_mb=18432,
    )
    assert prof.name == "qwen3:30b"
    assert prof.role == ModelRole.HEAVY
    assert prof.size_class == ModelSizeClass.LARGE
    assert prof.capabilities.reasoning_level == ReasoningLevel.EXPERT
    assert prof.capabilities.tool_calling is True


def test_model_capabilities_defaults() -> None:
    caps = ModelCapabilities()
    assert caps.tool_calling is True
    assert caps.json_mode is True
    assert caps.reasoning_level == ReasoningLevel.MODERATE
    assert caps.context_length == 16384
