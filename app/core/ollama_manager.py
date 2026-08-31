"""Lifecycle manager for local Ollama server detection, discovery, and automated execution."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Optional
import urllib.request
import json

from app.core.config import Settings, get_settings
from app.core.exceptions import OllamaConnectionError
from app.core.logging import get_logger

logger = get_logger("core.ollama_manager")

# Windows process creation flags to hide console window in background/GUI mode
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class OllamaManager:
    """Manages Ollama server discovery, background startup, readiness polling, and lifecycle."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings: Settings = settings or get_settings()
        self.base_url: str = self.settings.ollama_base_url.rstrip("/")
        self.started_by_app: bool = False
        self._process: Optional[subprocess.Popen] = None

    def is_server_running(self) -> bool:
        """Check if the Ollama API server is reachable and responding."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", headers={"User-Agent": "LocalAssistant/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        return False

    def find_executable(self) -> Optional[Path]:
        """Locate the Ollama binary using configuration, PATH, or standard Windows paths."""
        # 1. Explicit configuration
        if self.settings.ollama_executable:
            p = Path(self.settings.ollama_executable)
            if p.exists() and p.is_file():
                return p.resolve()

        # 2. System PATH
        which_path = shutil.which("ollama")
        if which_path:
            return Path(which_path).resolve()

        # 3. Standard Windows locations
        if sys.platform == "win32":
            candidates: list[Path] = []
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                candidates.append(Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe")
                candidates.append(Path(local_appdata) / "Ollama" / "ollama.exe")

            program_files = os.environ.get("ProgramFiles")
            if program_files:
                candidates.append(Path(program_files) / "Ollama" / "ollama.exe")

            program_files_x86 = os.environ.get("ProgramFiles(x86)")
            if program_files_x86:
                candidates.append(Path(program_files_x86) / "Ollama" / "ollama.exe")

            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                candidates.append(Path(user_profile) / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe")

            for c in candidates:
                if c.exists() and c.is_file():
                    return c.resolve()

        return None

    def start_server(self, wait_seconds: float = 30.0) -> bool:
        """Start Ollama background process if not already active and wait until healthy."""
        if self.is_server_running():
            logger.info("Ollama server is already active on %s (reusing instance).", self.base_url)
            self.started_by_app = False
            return True

        if not self.settings.auto_start_ollama:
            logger.warning("Ollama is not running and auto_start_ollama is disabled.")
            return False

        exe_path = self.find_executable()
        if not exe_path:
            logger.error("Could not find Ollama executable on this system.")
            return False

        logger.info("Starting local Ollama server process via '%s'...", exe_path)
        try:
            # Launch without opening a visible command prompt window
            creation_flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = subprocess.Popen(
                [str(exe_path), "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
                close_fds=True if sys.platform != "win32" else False,
            )
            self.started_by_app = True
            logger.info("Ollama process spawned (PID: %s). Waiting for API readiness...", self._process.pid)
            ready = self.wait_until_ready(timeout=wait_seconds)
            if not ready:
                logger.error("Timed out waiting for Ollama API to become ready after %ss.", wait_seconds)
                return False
            logger.info("Ollama server is ready and responding at %s.", self.base_url)
            return True
        except Exception as err:
            logger.error("Failed to start Ollama server: %s", err)
            self.started_by_app = False
            return False

    def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """Poll the server until healthy or timeout expires."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_server_running():
                return True
            time.sleep(0.5)
        return False

    def list_available_models(self) -> list[str]:
        """Query list of models currently installed in Ollama."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", headers={"User-Agent": "LocalAssistant/1.0"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = data.get("models", [])
                    return [m.get("name") or m.get("model") for m in models if (m.get("name") or m.get("model"))]
        except Exception as err:
            logger.warning("Could not list Ollama models: %s", err)
        return []

    def is_model_available(self, model_name: str) -> bool:
        """Check if target model is present in the Ollama store."""
        available = self.list_available_models()
        if model_name in available:
            return True
        # Match tag prefix (e.g. 'qwen3:30b' matches 'qwen3:30b')
        base_name = model_name.split(":")[0]
        for m in available:
            if m == model_name or m.split(":")[0] == base_name:
                return True
        return False

    def preload_model_if_requested(self, model_name: Optional[str] = None) -> bool:
        """Optionally warm up model in memory if PRELOAD_MODEL is enabled."""
        if not self.settings.preload_model:
            return False

        target = model_name or self.settings.default_model
        logger.info("Preloading model '%s' into Ollama memory...", target)
        try:
            payload = json.dumps({"model": target, "keep_alive": self.settings.ollama_keep_alive or "5m"}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "LocalAssistant/1.0"},
            )
            preload_timeout = max(300.0, getattr(self.settings, "ollama_timeout_seconds", 300.0))
            with urllib.request.urlopen(req, timeout=preload_timeout) as resp:
                return resp.status == 200
        except Exception as err:
            logger.warning("Model preload failed: %s", err)
            return False

    def get_status(self, model_name: Optional[str] = None) -> dict[str, Any]:
        """Return structured diagnostic status for Ollama and model availability."""
        running = self.is_server_running()
        models = self.list_available_models() if running else []
        target = model_name or self.settings.default_model
        model_ready = target in models or any(m.split(":")[0] == target.split(":")[0] for m in models)

        return {
            "server_running": running,
            "base_url": self.base_url,
            "executable_path": str(self.find_executable()) if self.find_executable() else None,
            "started_by_app": self.started_by_app,
            "pid": self._process.pid if self._process else None,
            "target_model": target,
            "model_available": model_ready,
            "available_models": models,
        }

    def stop_if_owned(self) -> None:
        """Terminate the Ollama server only if this application instance spawned it."""
        if not self.started_by_app or not self._process:
            logger.debug("Ollama was not started by this application; leaving it running.")
            return

        if not self.settings.stop_ollama_on_exit:
            logger.info("Preserving Ollama server process (stop_ollama_on_exit is False).")
            return

        logger.info("Terminating owned Ollama server process (PID: %s)...", self._process.pid)
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
            logger.info("Ollama server process stopped cleanly.")
        except Exception as err:
            logger.warning("Error stopping Ollama process: %s", err)
        finally:
            self._process = None
            self.started_by_app = False
