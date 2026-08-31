"""Safe application management tools with strict whitelist enforcement."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.core.logging import get_logger
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.system import SystemProvider

logger = get_logger("tools.applications")


class ApplicationDefinition(BaseModel):
    """Configuration for a whitelisted application."""

    logical_name: str
    display_name: str
    executable_candidates: list[str]
    process_names: list[str]


class ApplicationRegistry:
    """Whitelist registry of approved desktop applications."""

    def __init__(self, custom_apps: Optional[dict[str, ApplicationDefinition]] = None) -> None:
        self._apps: dict[str, ApplicationDefinition] = {}

        # Register default safe applications
        self._register_default(ApplicationDefinition(
            logical_name="notepad",
            display_name="Notepad",
            executable_candidates=["notepad.exe", "notepad"],
            process_names=["notepad.exe"],
        ))
        self._register_default(ApplicationDefinition(
            logical_name="calculator",
            display_name="Windows Calculator",
            executable_candidates=["calc.exe", "calc"],
            process_names=["calc.exe", "calculator.exe", "CalculatorApp.exe"],
        ))
        self._register_default(ApplicationDefinition(
            logical_name="vscode",
            display_name="Visual Studio Code",
            executable_candidates=["code.cmd", "code.exe", "Code.exe"],
            process_names=["code.exe"],
        ))
        self._register_default(ApplicationDefinition(
            logical_name="chrome",
            display_name="Google Chrome",
            executable_candidates=[
                "chrome.exe",
                "C:/Program Files/Google/Chrome/Application/chrome.exe",
                "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            ],
            process_names=["chrome.exe"],
        ))
        self._register_default(ApplicationDefinition(
            logical_name="edge",
            display_name="Microsoft Edge",
            executable_candidates=[
                "msedge.exe",
                "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
                "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
            ],
            process_names=["msedge.exe"],
        ))
        self._register_default(ApplicationDefinition(
            logical_name="paint",
            display_name="Paint",
            executable_candidates=["mspaint.exe", "mspaint"],
            process_names=["mspaint.exe"],
        ))

        # Add custom apps if provided
        if custom_apps:
            for k, app in custom_apps.items():
                self._apps[k.lower()] = app

    def _register_default(self, app: ApplicationDefinition) -> None:
        self._apps[app.logical_name.lower()] = app

    def list_names(self) -> list[str]:
        return sorted(list(self._apps.keys()))

    def get(self, name: str) -> Optional[ApplicationDefinition]:
        if not name or not isinstance(name, str):
            return None
        normalized = name.lower().strip()
        # Aliases
        if normalized in ("calc",):
            normalized = "calculator"
        elif normalized in ("code", "visual studio code"):
            normalized = "vscode"
        elif normalized in ("google chrome",):
            normalized = "chrome"
        elif normalized in ("microsoft edge",):
            normalized = "edge"
        return self._apps.get(normalized)

    def is_whitelisted(self, name: str) -> bool:
        return self.get(name) is not None

    def resolve_executable(self, name: str) -> Optional[str]:
        app = self.get(name)
        if not app:
            return None

        for candidate in app.executable_candidates:
            # Check if direct existing path
            cand_path = Path(candidate)
            if cand_path.is_absolute() and cand_path.is_file():
                return str(cand_path)

            # Check system PATH via shutil.which
            found = shutil.which(candidate)
            if found:
                return found

        return None


# --- Parameter Schemas ---

class ApplicationTargetArgs(BaseModel):
    app_name: str = Field(
        description="Logical name of the approved application (e.g. 'notepad', 'calculator', 'vscode', 'chrome', 'edge', 'paint')"
    )


class CloseApplicationArgs(BaseModel):
    app_name: str = Field(
        description="Logical name of the approved application to close (e.g. 'notepad', 'calculator', 'chrome')"
    )
    force: bool = Field(
        default=False,
        description="If True, force-terminates process if graceful close is ignored",
    )


# --- Application Tools ---

class OpenApplicationTool(Tool):
    """Safely launches an approved application without shell execution."""

    def __init__(
        self,
        registry: Optional[ApplicationRegistry] = None,
        system_provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="open_application",
            description="Launch an approved desktop application from the whitelist without shell execution.",
            risk_level=RiskLevel.LOW,
            args_model=ApplicationTargetArgs,
        )
        self.registry = registry or ApplicationRegistry()
        self.system_provider = system_provider or SystemProvider()
        self.settings = settings or get_settings()

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        app_name = validated.get("app_name", "")

        # Strict whitelist rejection before permission checks
        if not self.registry.is_whitelisted(app_name):
            valid_apps = ", ".join(self.registry.list_names())
            raise ToolValidationError(
                f"Application '{app_name}' is not in the approved whitelist. Whitelisted applications: {valid_apps}"
            )
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        app_name = args["app_name"]
        app = self.registry.get(app_name)
        if not app:
            return ToolResult(success=False, error=f"Unknown application '{app_name}'")

        exe = self.registry.resolve_executable(app_name)
        if not exe:
            return ToolResult(
                success=False,
                error=f"Executable for '{app.display_name}' could not be located on this system",
            )

        try:
            # Direct process invocation without shell
            subprocess.Popen([exe], shell=False)

            # Post-launch verification: wait for matching process to appear
            timeout = self.settings.application_launch_timeout_seconds
            start_time = time.time()
            verified = False
            found_pids: list[int] = []

            while time.time() - start_time < timeout:
                time.sleep(0.3)
                procs = self.system_provider.list_processes(limit=1000)
                matching = [
                    p["pid"] for p in procs
                    if p["name"].lower() in [pn.lower() for pn in app.process_names]
                ]
                if matching:
                    verified = True
                    found_pids = matching
                    break

            return ToolResult(
                success=True,
                data={
                    "app_name": app.logical_name,
                    "display_name": app.display_name,
                    "executable": exe,
                    "verified": verified,
                    "pids": found_pids,
                },
                message=f"Launched '{app.display_name}'" + (f" (verified PIDs: {found_pids})." if verified else "."),
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to launch '{app.display_name}': {err}")


class CloseApplicationTool(Tool):
    """Gracefully closes matching processes for an approved application."""

    def __init__(
        self,
        registry: Optional[ApplicationRegistry] = None,
        system_provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="close_application",
            description="Close all active windows/processes of an approved application. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=CloseApplicationArgs,
        )
        self.registry = registry or ApplicationRegistry()
        self.system_provider = system_provider or SystemProvider()
        self.settings = settings or get_settings()

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        app_name = validated.get("app_name", "")

        if not self.registry.is_whitelisted(app_name):
            valid_apps = ", ".join(self.registry.list_names())
            raise ToolValidationError(
                f"Application '{app_name}' is not in the approved whitelist. Whitelisted applications: {valid_apps}"
            )
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        app_name = args["app_name"]
        force = args.get("force", False)

        app = self.registry.get(app_name)
        if not app:
            return ToolResult(success=False, error=f"Unknown application '{app_name}'")

        # Find matching running processes
        procs = self.system_provider.list_processes(limit=1000)
        target_pids = [
            p["pid"] for p in procs
            if p["name"].lower() in [pn.lower() for pn in app.process_names]
        ]

        if not target_pids:
            return ToolResult(
                success=True,
                data={"app_name": app.logical_name, "closed_count": 0, "status": "not_running"},
                message=f"Application '{app.display_name}' is not currently running.",
            )

        closed_pids: list[int] = []
        for pid in target_pids:
            try:
                # On Windows, try graceful close via taskkill /PID without /F
                cmd = ["taskkill", "/PID", str(pid)]
                if force:
                    cmd.append("/F")
                subprocess.run(cmd, capture_output=True, timeout=3.0, check=False)
                closed_pids.append(pid)
            except Exception as err:
                logger.warning("Failed closing PID %d: %s", pid, err)

        # Post-operation verification: ensure processes have exited
        timeout = self.settings.application_close_timeout_seconds
        start_time = time.time()
        all_closed = False

        while time.time() - start_time < timeout:
            time.sleep(0.3)
            current_procs = self.system_provider.list_processes(limit=1000)
            still_running = [
                p["pid"] for p in current_procs
                if p["name"].lower() in [pn.lower() for pn in app.process_names]
            ]
            if not still_running:
                all_closed = True
                break

        if not all_closed:
            return ToolResult(
                success=False,
                data={"app_name": app.logical_name, "attempted_pids": target_pids},
                error=f"Application '{app.display_name}' refused to exit within timeout ({timeout}s).",
            )

        return ToolResult(
            success=True,
            data={"app_name": app.logical_name, "closed_pids": closed_pids, "verified": True},
            message=f"Successfully closed '{app.display_name}' (PIDs: {closed_pids}).",
        )


class IsApplicationRunningTool(Tool):
    """Checks if an approved application is currently active."""

    def __init__(
        self,
        registry: Optional[ApplicationRegistry] = None,
        system_provider: Optional[SystemProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="is_application_running",
            description="Check if an approved desktop application has active processes running.",
            risk_level=RiskLevel.READ,
            args_model=ApplicationTargetArgs,
        )
        self.registry = registry or ApplicationRegistry()
        self.system_provider = system_provider or SystemProvider()
        self.settings = settings or get_settings()

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        app_name = validated.get("app_name", "")

        if not self.registry.is_whitelisted(app_name):
            valid_apps = ", ".join(self.registry.list_names())
            raise ToolValidationError(
                f"Application '{app_name}' is not in the approved whitelist. Whitelisted applications: {valid_apps}"
            )
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        app_name = args["app_name"]
        app = self.registry.get(app_name)
        if not app:
            return ToolResult(success=False, error=f"Unknown application '{app_name}'")

        procs = self.system_provider.list_processes(limit=1000)
        matching = [
            p["pid"] for p in procs
            if p["name"].lower() in [pn.lower() for pn in app.process_names]
        ]

        is_running = len(matching) > 0
        return ToolResult(
            success=True,
            data={
                "app_name": app.logical_name,
                "display_name": app.display_name,
                "running": is_running,
                "process_count": len(matching),
                "pids": matching,
            },
            message=f"'{app.display_name}' is {'running' if is_running else 'not running'} ({len(matching)} processes).",
        )
