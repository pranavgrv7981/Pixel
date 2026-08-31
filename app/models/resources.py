"""Resource management, memory pressure checks, and model warm-up controls."""

import sys
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.ollama_client import OllamaClient
from app.models.profiles import ModelProfile

logger = get_logger("models.resources")


class ModelResourceManager:
    """Monitors system memory pressure using standard library ctypes and controls safe model warming."""

    def __init__(self, client: OllamaClient, settings: Optional[Settings] = None) -> None:
        self.client = client
        self.settings = settings or get_settings()
        self.is_windows = sys.platform == "win32"

    def get_memory_info(self) -> dict[str, float]:
        """Return system RAM metrics in gigabytes."""
        if not self.is_windows:
            return {"total_gb": 16.0, "available_gb": 8.0, "used_percent": 50.0}

        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))

            total_gb = round(stat.ullTotalPhys / (1024**3), 2)
            avail_gb = round(stat.ullAvailPhys / (1024**3), 2)
            return {
                "total_gb": total_gb,
                "available_gb": avail_gb,
                "used_percent": float(stat.dwMemoryLoad),
            }
        except Exception as err:
            logger.warning("Could not query Windows memory status: %s", err)
            return {"total_gb": 16.0, "available_gb": 8.0, "used_percent": 50.0}

    def check_memory_pressure(self) -> tuple[bool, str]:
        """Check if system is under severe RAM pressure (> 90% utilized or < 2 GB free)."""
        info = self.get_memory_info()
        used_pct = info["used_percent"]
        avail_gb = info["available_gb"]

        if used_pct > 90.0 or avail_gb < 2.0:
            return True, f"High RAM pressure: {used_pct}% used ({avail_gb:.1f} GB available)."
        return False, f"Normal RAM state: {used_pct}% used ({avail_gb:.1f} GB available)."

    def can_safely_load(self, profile: ModelProfile) -> tuple[bool, Optional[str]]:
        """Verify if system has sufficient available RAM to host the model."""
        info = self.get_memory_info()
        available_mb = info["available_gb"] * 1024.0

        # Buffer: require 1.5 GB extra headroom
        required_mb = profile.estimated_ram_mb + 1536
        if available_mb < required_mb:
            return (
                False,
                f"Insufficient memory for {profile.name} (requires ~{profile.estimated_ram_mb} MB, {available_mb:.0f} MB available)",
            )
        return True, None

    def warmup_if_configured(self, model_name: str) -> bool:
        """Send a lightweight 1-token prompt to pre-warm a model in Ollama if enabled."""
        if not self.settings.preload_fast_model and not self.settings.preload_heavy_model:
            return False

        logger.info("Pre-warming model '%s'...", model_name)
        try:
            self.client.chat([{"role": "user", "content": "ping"}], model=model_name)
            logger.info("Model '%s' successfully warmed.", model_name)
            return True
        except Exception as err:
            logger.warning("Could not pre-warm model '%s': %s", model_name, err)
            return False
