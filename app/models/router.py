"""Model router orchestrating dynamic local model selection, capability verification, and safe fallbacks."""

from typing import Any, Optional
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import ModelNotFoundError
from app.core.logging import get_logger
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelProfile, ModelRole, ReasoningLevel
from app.models.registry import ModelRegistry
from app.models.selector import ModelSelector, RequestCategory, RequestClassifier

logger = get_logger("models.router")


class RoutingDecision(BaseModel):
    """Complete routing decision metadata for a given user request."""

    selected_model: str = Field(description="Exact Ollama model name selected for inference")
    role: ModelRole = Field(description="Target model role")
    category: RequestCategory = Field(description="Classified request type")
    reason: str = Field(description="Concise diagnostic rationale for model selection")
    fallback_model: Optional[str] = Field(default=None, description="Original requested model if fallback occurred")
    is_fallback: bool = Field(default=False, description="Whether a fallback model was used")
    context_bytes: int = Field(default=0, description="Evaluated context size in bytes")


class ModelRouter:
    """Intelligent local model router matching task complexity to optimal Ollama models with safe fallbacks."""

    def __init__(
        self,
        registry: ModelRegistry,
        availability_checker: ModelAvailabilityChecker,
        selector: Optional[ModelSelector] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.registry = registry
        self.availability_checker = availability_checker
        self.selector = selector or ModelSelector(settings=settings)
        self.settings = settings or get_settings()

    def route_request(
        self,
        prompt: str,
        is_planning: bool = False,
        is_background: bool = False,
        has_images: bool = False,
        explicit_mode: Optional[str] = None,
        context_bytes: int = 0,
    ) -> RoutingDecision:
        """Select the best available model for the request based on mode, complexity, and availability."""
        mode = (explicit_mode or self.settings.model_routing_mode).strip().lower()
        category = RequestClassifier.classify(prompt, is_planning=is_planning, is_background=is_background)
        installed_models = self.availability_checker.list_installed_models()

        if has_images:
            # Route to a verified vision-capable model
            vision_models = [
                p for p in self.registry.list_vision_models()
                if self.availability_checker._model_matches(p.name, installed_models)
            ]
            # Also check if any installed model matches common vision tags
            if not vision_models:
                for inst in installed_models:
                    inst_lower = inst.lower()
                    if any(tag in inst_lower for tag in ("llava", "minicpm-v", "qwen2.5-vl", "llama3.2-vision", "moondream", "bakllava")):
                        vision_models.append(ModelProfile(
                            name=inst,
                            role=ModelRole.VISION,
                            capabilities=self.registry.get(inst).capabilities if self.registry.has(inst) else None or ModelProfile(name=inst).capabilities,
                        ))
                        break

            if vision_models:
                selected = vision_models[0].name
                return RoutingDecision(
                    selected_model=selected,
                    role=ModelRole.VISION,
                    category=category,
                    reason=f"Vision model selected for multimodal input: {selected}",
                    context_bytes=context_bytes,
                )
            else:
                logger.warning("Multimodal image input provided, but no vision-capable model is installed in Ollama.")
                return RoutingDecision(
                    selected_model="",
                    role=ModelRole.VISION,
                    category=category,
                    reason="No vision-capable local model installed.",
                    context_bytes=context_bytes,
                )

        if not installed_models:
            # Server offline or no models installed: return configured default with warning
            logger.warning("No installed models detected from Ollama; using default '%s'", self.settings.default_model)
            return RoutingDecision(
                selected_model=self.settings.default_model,
                role=ModelRole.HEAVY,
                category=category,
                reason="Default model selected (Ollama model list offline/empty).",
                context_bytes=context_bytes,
            )

        # 1. Explicit Model Name Override (e.g. user selected 'qwen3:30b' directly)
        if mode not in {"auto", "fast", "standard", "heavy"}:
            target_profile = self.registry.get(mode)
            target_name = target_profile.name if target_profile else mode
            if self.availability_checker._model_matches(target_name, installed_models):
                role = target_profile.role if target_profile else ModelRole.STANDARD
                return RoutingDecision(
                    selected_model=target_name,
                    role=role,
                    category=category,
                    reason=f"Explicit model override requested: {target_name}",
                    context_bytes=context_bytes,
                )
            # If explicit model is missing, handle fallback if enabled
            if not self.settings.model_fallback_enabled:
                raise ModelNotFoundError(f"Explicitly requested model '{target_name}' is not installed.")
            fallback_target = self._find_first_available_model(installed_models)
            return RoutingDecision(
                selected_model=fallback_target,
                role=ModelRole.STANDARD,
                category=category,
                reason=f"Requested model '{target_name}' not installed. Fallback to '{fallback_target}'.",
                fallback_model=target_name,
                is_fallback=True,
                context_bytes=context_bytes,
            )

        # 2. Explicit Role Override (e.g. user selected 'fast', 'standard', or 'heavy')
        if mode in {"fast", "standard", "heavy"}:
            role = ModelRole(mode)
            candidate = self.registry.get_default_for_role(role)
            target_name = candidate.name if candidate else self._get_configured_role_name(role)
            if self.availability_checker._model_matches(target_name, installed_models):
                return RoutingDecision(
                    selected_model=target_name,
                    role=role,
                    category=category,
                    reason=f"Explicit role override: {role.value.upper()} ({target_name})",
                    context_bytes=context_bytes,
                )
            # Fallback for missing role model
            return self._resolve_role_fallback(role, category, target_name, installed_models, context_bytes)

        # 3. Dynamic AUTO Routing Mode
        target_role, reason = self.selector.select_role(category, context_bytes=context_bytes)
        candidate = self.registry.get_default_for_role(target_role)
        target_name = candidate.name if candidate else self._get_configured_role_name(target_role)

        # Check if preferred candidate is installed
        if self.availability_checker._model_matches(target_name, installed_models):
            return RoutingDecision(
                selected_model=target_name,
                role=target_role,
                category=category,
                reason=f"Auto routing: {reason}",
                context_bytes=context_bytes,
            )

        # Preferred model is missing -> perform structured role fallback
        return self._resolve_role_fallback(target_role, category, target_name, installed_models, context_bytes)

    def _resolve_role_fallback(
        self,
        desired_role: ModelRole,
        category: RequestCategory,
        missing_target: str,
        installed_models: list[str],
        context_bytes: int,
    ) -> RoutingDecision:
        """Resolve fallback when the preferred model for a role is not installed."""
        if not self.settings.model_fallback_enabled:
            raise ModelNotFoundError(f"Preferred model '{missing_target}' for {desired_role.value} is not installed.")

        # Fallback Priority Matrix
        fallback_order: list[ModelRole] = []
        if desired_role == ModelRole.FAST:
            fallback_order = [ModelRole.STANDARD, ModelRole.HEAVY]
        elif desired_role == ModelRole.STANDARD:
            fallback_order = [ModelRole.HEAVY, ModelRole.FAST]
        elif desired_role == ModelRole.HEAVY:
            fallback_order = [ModelRole.STANDARD, ModelRole.FAST]

        for alt_role in fallback_order:
            alt_prof = self.registry.get_default_for_role(alt_role)
            alt_name = alt_prof.name if alt_prof else self._get_configured_role_name(alt_role)
            if self.availability_checker._model_matches(alt_name, installed_models):
                logger.info(
                    "Model fallback: '%s' (%s) not installed -> routing to '%s' (%s)",
                    missing_target,
                    desired_role.value,
                    alt_name,
                    alt_role.value,
                )
                return RoutingDecision(
                    selected_model=alt_name,
                    role=alt_role,
                    category=category,
                    reason=f"Preferred {desired_role.value} model '{missing_target}' unavailable. Fallback to '{alt_name}'.",
                    fallback_model=missing_target,
                    is_fallback=True,
                    context_bytes=context_bytes,
                )

        # If none of the registered role models match, pick any installed model
        fallback_model = self._find_first_available_model(installed_models)
        return RoutingDecision(
            selected_model=fallback_model,
            role=ModelRole.STANDARD,
            category=category,
            reason=f"No configured role models installed. Fallback to available '{fallback_model}'.",
            fallback_model=missing_target,
            is_fallback=True,
            context_bytes=context_bytes,
        )

    def _find_first_available_model(self, installed_models: list[str]) -> str:
        """Return the best installed model available on Ollama."""
        # Prioritize 30b/heavy or 8b/standard if installed
        for name in installed_models:
            if isinstance(name, str) and ("30b" in name.lower() or "heavy" in name.lower()):
                return str(name)
        for name in installed_models:
            if isinstance(name, str) and ("8b" in name.lower() or "7b" in name.lower()):
                return str(name)
        for name in installed_models:
            if isinstance(name, str) and name.strip():
                return str(name)
        return self.settings.default_model


    def _get_configured_role_name(self, role: ModelRole) -> str:
        """Get model tag configured in settings for a role."""
        if role == ModelRole.FAST:
            return self.settings.fast_model
        if role == ModelRole.STANDARD:
            return self.settings.standard_model
        if role == ModelRole.HEAVY:
            return self.settings.heavy_model
        return self.settings.default_model

    def filter_tools_for_request(
        self,
        category: RequestCategory,
        all_schemas: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Lightweight tool schema exposure to avoid overwhelming smaller models during simple chat."""
        if not all_schemas:
            return []

        # For simple greetings or conversational chat without tool intents, expose minimal core tools
        if category == RequestCategory.SIMPLE_CHAT:
            allowed_names = {"get_current_time", "calculate", "get_system_info", "recall_memory"}
            return [s for s in all_schemas if s.get("function", {}).get("name") in allowed_names]

        # For specific tool domains, provide full schema set (generic tool system is preserved)
        return all_schemas
