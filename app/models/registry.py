"""In-memory model registry managing registered profiles and role assignments."""

from typing import Optional
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.profiles import (
    ModelCapabilities,
    ModelProfile,
    ModelRole,
    ModelSizeClass,
    ReasoningLevel,
)

logger = get_logger("models.registry")


class DuplicateModelError(Exception):
    """Raised when registering a model profile that is already registered."""

    pass


class ModelRegistry:
    """Stores and indexes ModelProfiles by name, role, and capabilities."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._profiles: dict[str, ModelProfile] = {}
        self._register_default_profiles()

    def register(self, profile: ModelProfile) -> None:
        """Register a new model profile. Rejects duplicate model names."""
        norm_name = profile.name.strip().lower()
        if norm_name in self._profiles:
            raise DuplicateModelError(f"Model profile '{profile.name}' is already registered.")

        self._profiles[norm_name] = profile
        logger.info(
            "Registered model profile '%s' [Role: %s, Size: %s]",
            profile.name,
            profile.role.value,
            profile.size_class.value,
        )

    def get(self, name: str) -> Optional[ModelProfile]:
        """Retrieve model profile by name (case-insensitive and tag-flexible)."""
        norm_name = name.strip().lower()
        if norm_name in self._profiles:
            return self._profiles[norm_name]

        # Tag-flexible lookup (e.g. qwen3:30b vs qwen3:30b:latest)
        base_name = norm_name.split(":")[0]
        for key, prof in self._profiles.items():
            if key.split(":")[0] == base_name:
                return prof
        return None

    def has(self, name: str) -> bool:
        """Return True if the model name is registered."""
        return self.get(name) is not None

    def remove(self, name: str) -> bool:
        """Unregister a model profile."""
        norm_name = name.strip().lower()
        if norm_name in self._profiles:
            del self._profiles[norm_name]
            logger.info("Unregistered model profile '%s'", name)
            return True
        return False

    def list(self) -> list[ModelProfile]:
        """Return all registered model profiles."""
        return list(self._profiles.values())

    def list_by_role(self, role: ModelRole) -> list[ModelProfile]:
        """Return all models assigned to a specific conceptual role."""
        return [p for p in self._profiles.values() if p.role == role]

    def get_default_for_role(self, role: ModelRole) -> Optional[ModelProfile]:
        """Get preferred or first registered model for a given role."""
        matches = self.list_by_role(role)
        for m in matches:
            if m.is_default:
                return m
        return matches[0] if matches else None

    def _register_default_profiles(self) -> None:
        """Seed registry with configured Fast, Standard, and Heavy model profiles."""
        fast = ModelProfile(
            name=self.settings.fast_model,
            size_class=ModelSizeClass.TINY,
            role=ModelRole.FAST,
            capabilities=ModelCapabilities(
                tool_calling=True,
                json_mode=True,
                reasoning_level=ReasoningLevel.BASIC,
                context_length=8192,
            ),
            preferred_for=["greetings", "simple_chat", "direct_tool", "formatting", "short_summary"],
            is_default=True,
            description="Ultra-fast lightweight model for simple queries, conversational turns, and instant responses.",
            estimated_ram_mb=1024,
        )

        standard = ModelProfile(
            name=self.settings.standard_model,
            size_class=ModelSizeClass.MEDIUM,
            role=ModelRole.STANDARD,
            capabilities=ModelCapabilities(
                tool_calling=True,
                json_mode=True,
                reasoning_level=ReasoningLevel.ADVANCED,
                context_length=16384,
            ),
            preferred_for=["rag_query", "code_task", "knowledge_synthesis", "memory_query", "browser_task"],
            is_default=True,
            description="Balanced everyday model for tool calling, code analysis, document RAG, and memory recall.",
            estimated_ram_mb=6144,
        )

        heavy = ModelProfile(
            name=self.settings.heavy_model,
            size_class=ModelSizeClass.LARGE,
            role=ModelRole.HEAVY,
            capabilities=ModelCapabilities(
                tool_calling=True,
                json_mode=True,
                reasoning_level=ReasoningLevel.EXPERT,
                context_length=16384,
            ),
            preferred_for=["multi_step_planning", "complex_reasoning", "deep_debugging", "ambiguous_workflow"],
            is_default=True,
            description="Flagship powerhouse model for multi-step autonomous planning, deep reasoning, and complex tasks.",
            estimated_ram_mb=18432,
        )

        vision = ModelProfile(
            name=self.settings.vision_model,
            size_class=ModelSizeClass.MEDIUM,
            role=ModelRole.VISION,
            capabilities=ModelCapabilities(
                tool_calling=True,
                json_mode=True,
                reasoning_level=ReasoningLevel.ADVANCED,
                context_length=8192,
                vision=True,
            ),
            preferred_for=["image_understanding", "screenshot_analysis", "diagram_explanation", "visual_ocr", "error_image"],
            is_default=True,
            description="Multimodal vision model for image understanding, screenshot analysis, and diagram parsing.",
            estimated_ram_mb=6144,
        )

        self._profiles[fast.name.lower()] = fast
        self._profiles[standard.name.lower()] = standard
        self._profiles[heavy.name.lower()] = heavy
        self._profiles[vision.name.lower()] = vision

    def list_vision_models(self) -> list[ModelProfile]:
        """Return all registered model profiles supporting multimodal vision."""
        return [p for p in self._profiles.values() if p.capabilities.vision or p.role == ModelRole.VISION]
