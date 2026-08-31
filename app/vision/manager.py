"""Central VisionManager coordinating image preprocessing, caching, and model dispatch."""

import time
from typing import Optional, Union

from app.core.config import Settings, get_settings
from app.core.exceptions import ModelNotFoundError, ToolValidationError
from app.core.logging import get_logger
from app.core.ollama_client import OllamaClient
from app.models.availability import ModelAvailabilityChecker
from app.models.profiles import ModelProfile, ModelRole
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.vision.inputs import ImageInputLoader
from app.vision.models import ImageInput, VisionResult, VisionStatus
from app.vision.processor import ImageProcessor
from app.vision.providers import OllamaVisionProvider, VisionProvider

logger = get_logger("vision.manager")


class VisionManager:
    """Manages the full lifecycle of multimodal vision requests, caching, model routing, and cleanup."""

    def __init__(
        self,
        provider: Optional[VisionProvider] = None,
        processor: Optional[ImageProcessor] = None,
        input_loader: Optional[ImageInputLoader] = None,
        router: Optional[ModelRouter] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.processor = processor or ImageProcessor(settings=self.settings)
        self.input_loader = input_loader or ImageInputLoader(processor=self.processor, settings=self.settings)
        self.provider = provider or OllamaVisionProvider(settings=self.settings)

        # Model routing and availability checking
        if router is not None:
            self.router = router
        else:
            client = OllamaClient(settings=self.settings)
            reg = ModelRegistry(settings=self.settings)
            avail = ModelAvailabilityChecker(client=client, settings=self.settings)
            self.router = ModelRouter(registry=reg, availability_checker=avail, settings=self.settings)

        self._cache: dict[str, tuple[VisionResult, float]] = {}

    def get_status(self) -> VisionStatus:
        """Inspect installed models to determine whether multimodal vision is available."""
        if not self.settings.vision_enabled:
            return VisionStatus(
                is_available=False,
                active_model=None,
                installed_vision_models=[],
                error_message="Vision subsystem is disabled in configuration.",
            )

        installed = self.router.availability_checker.list_installed_models()
        vision_candidates: list[str] = []

        for inst in installed:
            inst_lower = inst.lower()
            prof = self.router.registry.get(inst)
            if (prof and prof.capabilities.vision) or any(
                tag in inst_lower for tag in ("llava", "minicpm-v", "qwen2.5-vl", "llama3.2-vision", "moondream", "bakllava")
            ):
                vision_candidates.append(inst)

        if vision_candidates:
            return VisionStatus(
                is_available=True,
                active_model=vision_candidates[0],
                installed_vision_models=vision_candidates,
                error_message=None,
            )
        else:
            return VisionStatus(
                is_available=False,
                active_model=None,
                installed_vision_models=[],
                error_message="No vision-capable local model installed.",
            )

    def analyze_images(
        self,
        images: list[ImageInput],
        prompt: str = "Describe this image in detail.",
        model_name: Optional[str] = None,
    ) -> VisionResult:
        """Execute multimodal vision inference with input bounding, routing, caching, and cleanup."""
        if not images:
            raise ToolValidationError("No image inputs provided for vision analysis.")

        if len(images) > self.settings.max_images_per_request:
            raise ToolValidationError(
                f"Number of attached images ({len(images)}) exceeds maximum allowed per request ({self.settings.max_images_per_request})"
            )

        # 1. Resolve Target Vision Model
        status = self.get_status()
        target_model = model_name or status.active_model
        if not target_model:
            raise ModelNotFoundError(
                "Vision analysis unavailable: No vision-capable local model is installed on the Ollama server."
            )

        # 2. Check Cache
        cache_key = f"{target_model}:{prompt}:{'-'.join(img.sha256_hash for img in images)}"
        now = time.time()
        if cache_key in self._cache:
            cached_res, timestamp = self._cache[cache_key]
            if now - timestamp < self.settings.image_cache_ttl_seconds:
                logger.info("Serving vision result from cache (TTL %.1fs remaining)", self.settings.image_cache_ttl_seconds - (now - timestamp))
                return cached_res

        # 3. Execute Vision Provider
        try:
            result = self.provider.analyze(image_inputs=images, prompt=prompt, model_name=target_model)
            self._cache[cache_key] = (result, now)
            return result
        finally:
            # 4. Clean up any temporary files generated during capture
            for img in images:
                if img.is_temp:
                    self.processor.cleanup_temp_file(img)
