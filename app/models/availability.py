"""Availability checking, discovery, and runtime presence detection for local models."""

from typing import Optional
from pydantic import BaseModel, Field
import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import OllamaConnectionError
from app.core.logging import get_logger
from app.core.ollama_client import OllamaClient
from app.models.profiles import ModelProfile, ModelRole
from app.models.registry import ModelRegistry

logger = get_logger("models.availability")


class ModelAvailabilityStatus(BaseModel):
    """Real-time availability and installation state of a model."""

    name: str
    role: Optional[ModelRole] = None
    configured: bool = True
    installed: bool = False
    available: bool = False
    currently_loaded: bool = False
    size_bytes: Optional[int] = None
    details: Optional[str] = None


class ModelAvailabilityChecker:
    """Interrogates local Ollama server to verify which registered and configured models are installed."""

    def __init__(self, client: OllamaClient, settings: Optional[Settings] = None) -> None:
        self.client = client
        self.settings = settings or get_settings()

    def list_installed_models(self) -> list[str]:
        """Fetch list of all installed model tags from Ollama."""
        try:
            raw = self.client.list_models()
            if not isinstance(raw, list):
                return []
            return [str(m) for m in raw if isinstance(m, (str, bytes))]
        except OllamaConnectionError:
            logger.warning("Ollama server unreachable when querying installed models.")
            return []
        except Exception as err:
            logger.warning("Error fetching model list from Ollama: %s", err)
            return []


    def check_availability(self, model: ModelProfile | str) -> ModelAvailabilityStatus:
        """Evaluate detailed availability status for a model profile or name."""
        name = model.name if isinstance(model, ModelProfile) else model
        role = model.role if isinstance(model, ModelProfile) else None

        installed_list = self.list_installed_models()
        is_installed = self._model_matches(name, installed_list)
        loaded_list = self.get_loaded_models()
        is_loaded = self._model_matches(name, loaded_list)

        status = ModelAvailabilityStatus(
            name=name,
            role=role,
            configured=True,
            installed=is_installed,
            available=is_installed,
            currently_loaded=is_loaded,
            details="Installed and ready" if is_installed else "Not installed on local Ollama server",
        )
        return status

    def get_all_statuses(self, registry: ModelRegistry) -> list[ModelAvailabilityStatus]:
        """Return availability status for all models in the registry."""
        installed_list = self.list_installed_models()
        loaded_list = self.get_loaded_models()
        results: list[ModelAvailabilityStatus] = []

        for prof in registry.list():
            is_inst = self._model_matches(prof.name, installed_list)
            is_load = self._model_matches(prof.name, loaded_list)
            results.append(
                ModelAvailabilityStatus(
                    name=prof.name,
                    role=prof.role,
                    configured=True,
                    installed=is_inst,
                    available=is_inst,
                    currently_loaded=is_load,
                    details=f"{prof.size_class.value.title()} model" + (" (Loaded in VRAM)" if is_load else ""),
                )
            )
        return results

    def get_loaded_models(self) -> list[str]:
        """Query Ollama /api/ps endpoint to find models currently resident in memory/VRAM."""
        url = f"{self.client.base_url.rstrip('/')}/api/ps"
        try:
            with httpx.Client(timeout=2.0) as http:
                resp = http.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models_data = data.get("models", [])
                    return [m.get("name", "") for m in models_data if m.get("name")]
        except Exception:
            # Fall back silently if /api/ps is not supported or offline
            pass
        return []

    def _model_matches(self, target: str, available_models: list[str]) -> bool:
        """Match target model tag against available names."""
        if target in available_models:
            return True
        target_base = target.split(":")[0].lower()
        for name in available_models:
            norm_name = name.lower()
            if norm_name == target.lower():
                return True
            name_base = norm_name.split(":")[0]
            if norm_name == f"{target.lower()}:latest" or target.lower() == f"{norm_name}:latest":
                return True
            if ":" not in target and name_base == target_base:
                return True
        return False
