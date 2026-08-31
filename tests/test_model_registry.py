"""Unit tests for ModelRegistry registration, lookups, and duplicate rejection."""

import pytest
from app.models.profiles import (
    ModelCapabilities,
    ModelProfile,
    ModelRole,
    ModelSizeClass,
)
from app.models.registry import DuplicateModelError, ModelRegistry


def test_registry_default_seeding() -> None:
    reg = ModelRegistry()
    profiles = reg.list()
    assert len(profiles) >= 3
    assert reg.has("qwen3:30b") is True
    assert reg.has("qwen3:8b") is True
    assert reg.has("qwen2.5:0.5b") is True


def test_registry_rejects_duplicates() -> None:
    reg = ModelRegistry()
    dup = ModelProfile(name="qwen3:30b", size_class=ModelSizeClass.LARGE, role=ModelRole.HEAVY)
    with pytest.raises(DuplicateModelError):
        reg.register(dup)


def test_registry_list_by_role_and_remove() -> None:
    reg = ModelRegistry()
    heavy_models = reg.list_by_role(ModelRole.HEAVY)
    assert len(heavy_models) >= 1
    assert heavy_models[0].name == "qwen3:30b"

    removed = reg.remove("qwen2.5:0.5b")
    assert removed is True
    assert reg.has("qwen2.5:0.5b") is False
