"""Abstract and Ollama-backed multimodal vision providers."""

from abc import ABC, abstractmethod
import time
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import ModelAPIError, ModelNotFoundError
from app.core.logging import get_logger
from app.core.ollama_client import OllamaClient
from app.vision.models import ImageInput, VisionResult

logger = get_logger("vision.providers")


class VisionProvider(ABC):
    """Abstract interface for local multimodal vision inference providers."""

    @abstractmethod
    def analyze(self, image_inputs: list[ImageInput], prompt: str, model_name: str) -> VisionResult:
        """Analyze one or more image inputs using the given prompt and model."""
        pass


class OllamaVisionProvider(VisionProvider):
    """Local Ollama-backed multimodal vision provider passing base64 image payloads."""

    def __init__(self, client: Optional[OllamaClient] = None, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or OllamaClient(settings=self.settings)

    def analyze(self, image_inputs: list[ImageInput], prompt: str, model_name: str) -> VisionResult:
        """Execute multimodal vision inference via Ollama."""
        if not image_inputs:
            raise ValueError("At least one ImageInput is required for vision analysis.")

        if not model_name:
            raise ModelNotFoundError("No vision model specified for analysis.")

        # Extract base64 image strings
        images_payload = [img.base64_data for img in image_inputs if img.base64_data]
        if not images_payload:
            raise ValueError("Images do not contain valid base64 payloads.")

        messages = [
            {
                "role": "user",
                "content": prompt or "Describe the contents of this image in detail.",
                "images": images_payload,
            }
        ]

        logger.info(
            "Dispatching multimodal vision inference to model '%s' (%d images, prompt='%s')",
            model_name,
            len(images_payload),
            prompt[:80],
        )

        t0 = time.time()
        try:
            resp = self.client.chat(messages, model=model_name)
            elapsed = time.time() - t0

            content = resp.content if hasattr(resp, "content") else str(resp)
            logger.info("Vision inference completed in %.2fs (%d chars)", elapsed, len(content))

            return VisionResult(
                text=content.strip(),
                model=model_name,
                processing_time_seconds=round(elapsed, 3),
                metadata={
                    "image_count": len(image_inputs),
                    "dimensions": [img.dimensions_str for img in image_inputs],
                    "total_bytes": sum(img.size_bytes for img in image_inputs),
                },
            )
        except Exception as err:
            elapsed = time.time() - t0
            logger.error("Vision inference failed on model '%s' after %.2fs: %s", model_name, elapsed, err)
            raise
