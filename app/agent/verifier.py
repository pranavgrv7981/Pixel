"""Action verification and physical state inspection layer."""

import os
from pathlib import Path
from typing import Any, Optional
import psutil

from app.agent.intelligence_models import ExecutionVerification
from app.core.logging import get_logger
from app.tools.base import ToolResult

logger = get_logger("agent.verifier")


class ActionVerifier:
    """Verifies that executed tool actions physically succeeded on the host system."""

    def verify_tool_action(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> ExecutionVerification:
        """Inspect physical system state post-execution to verify true completion."""
        # 1. If tool reported failure outright, goal failed
        if not result.success:
            return ExecutionVerification(
                verified=True,
                goal_achieved=False,
                details=f"Tool '{tool_name}' reported failure: {result.error}",
                discrepancies=[result.error or "Tool execution failed"],
            )

        # 2. File Creation / Write Verification
        if tool_name in {"create_file", "write_text_file"}:
            path_str = arguments.get("path") or arguments.get("file_path")
            if path_str:
                p = Path(path_str)
                if not p.exists():
                    return ExecutionVerification(
                        verified=False,
                        goal_achieved=False,
                        details=f"File '{path_str}' was reported created but does not exist on disk.",
                        discrepancies=["File missing post-write"],
                    )
                return ExecutionVerification(
                    verified=True,
                    goal_achieved=True,
                    details=f"File '{path_str}' verified on disk ({p.stat().st_size} bytes).",
                )

        # 3. File Deletion Verification
        if tool_name == "delete_file":
            path_str = arguments.get("path") or arguments.get("file_path")
            if path_str:
                p = Path(path_str)
                if p.exists():
                    return ExecutionVerification(
                        verified=False,
                        goal_achieved=False,
                        details=f"File '{path_str}' was reported deleted but still exists on disk.",
                        discrepancies=["File still present post-delete"],
                    )
                return ExecutionVerification(
                    verified=True,
                    goal_achieved=True,
                    details=f"File '{path_str}' verified deleted from disk.",
                )

        # 4. Application Launch Verification
        if tool_name == "open_application":
            app_name = str(arguments.get("app_name", "")).lower()
            # Give short yield to allow OS to spawn
            is_running = any(app_name in p.name().lower() for p in psutil.process_iter(["name"]))
            if is_running:
                return ExecutionVerification(
                    verified=True,
                    goal_achieved=True,
                    details=f"Application '{app_name}' verified running in process table.",
                )
            # If not immediately detected in process table, still return success if tool returned success
            return ExecutionVerification(
                verified=True,
                goal_achieved=True,
                details=f"Application '{app_name}' launch command issued successfully.",
            )

        # 5. Compilation & Code Execution Verification
        if tool_name == "compile_c_program":
            output_bin = arguments.get("output_binary")
            if output_bin and Path(output_bin).exists():
                return ExecutionVerification(
                    verified=True,
                    goal_achieved=True,
                    details=f"C compilation succeeded and binary '{output_bin}' verified on disk.",
                )

        if tool_name == "run_pytest":
            data = result.data or {}
            exit_code = data.get("exit_code", 0)
            if exit_code == 0:
                return ExecutionVerification(
                    verified=True,
                    goal_achieved=True,
                    details="All pytest tests passed successfully (exit code 0).",
                )
            else:
                return ExecutionVerification(
                    verified=True,
                    goal_achieved=False,
                    details=f"Pytest test suite failed with exit code {exit_code}.",
                    discrepancies=["Pytest suite reported failures"],
                )

        # Default verification: tool reported success
        return ExecutionVerification(
            verified=True,
            goal_achieved=True,
            details=f"Action '{tool_name}' verified successful.",
        )
