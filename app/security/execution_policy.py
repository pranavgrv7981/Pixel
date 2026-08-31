"""Controlled process execution policy enforcing sandbox boundaries, timeouts, and output limits."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import SecurityError, ToolValidationError
from app.core.logging import get_logger
from app.tools.path_guard import PathGuard

if TYPE_CHECKING:
    from app.security.audit import AuditLogger

logger = get_logger("security.execution")



@dataclass
class ExecutionRequest:
    """Structured request for controlled process execution."""

    executable: str
    args: list[str] = field(default_factory=list)
    cwd: Optional[Path] = None
    timeout_seconds: Optional[float] = None
    max_output_bytes: Optional[int] = None
    env: Optional[dict[str, str]] = None


@dataclass
class ExecutionResult:
    """Structured result of controlled process execution."""

    success: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    truncated: bool
    cwd: str


class ExecutionPolicy:
    """Enforces strict process execution boundaries and resource limits."""

    FORBIDDEN_EXECUTABLES = {
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "cmd",
        "cmd.exe",
        "wscript",
        "wscript.exe",
        "cscript",
        "cscript.exe",
        "mshta",
        "mshta.exe",
        "bash",
        "bash.exe",
        "sh",
        "sh.exe",
        "zsh",
        "zsh.exe",
    }

    def __init__(
        self,
        path_guard: Optional[PathGuard] = None,
        audit_logger: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.path_guard = path_guard or PathGuard(settings=self.settings)
        if audit_logger is not None:
            self.audit_logger = audit_logger
        else:
            from app.security.audit import AuditLogger
            self.audit_logger = AuditLogger()


    def validate_executable(self, executable: str) -> str:
        """Verify executable is not in the forbidden shells/scripting blacklist."""
        if not executable or not isinstance(executable, str):
            raise ToolValidationError("Executable must be a non-empty string")

        raw = executable.strip()
        base_name = Path(raw).name.lower()

        if base_name in self.FORBIDDEN_EXECUTABLES:
            logger.warning("Execution blocked: forbidden executable '%s'", raw)
            raise SecurityError(f"Execution of shell/scripting engine '{raw}' is strictly forbidden")

        # Check if it is a trusted system runtime
        trusted_runtimes = {
            sys.executable.lower(),
            str(Path(sys.executable).resolve()).lower(),
        }
        for candidate in (
            self.settings.python_executable,
            self.settings.compiler_executable,
            self.settings.git_executable,
            shutil.which("git"),
            shutil.which("gcc"),
            shutil.which("clang"),
        ):
            if candidate:
                trusted_runtimes.add(candidate.lower())
                trusted_runtimes.add(str(Path(candidate).resolve()).lower())


        resolved_target = str(Path(raw).resolve()).lower() if (os.sep in raw or Path(raw).is_absolute()) else raw.lower()
        if raw.lower() in trusted_runtimes or resolved_target in trusted_runtimes:
            return raw

        # If it's a relative/absolute path to a binary inside the sandbox, validate it via PathGuard
        if os.sep in raw or (os.altsep and os.altsep in raw) or Path(raw).is_absolute():
            validated_path = self.path_guard.validate_path(raw, must_be_file=True)
            return str(validated_path)

        # Otherwise resolve via system PATH
        resolved = shutil.which(raw)
        if not resolved:
            raise ToolValidationError(f"Executable '{raw}' not found on system PATH")

        return resolved


    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a controlled command within sandbox boundaries with bounded time and output."""
        start_time = time.time()

        # 1. Validate executable
        resolved_exe = self.validate_executable(request.executable)

        # 2. Validate working directory
        cwd = request.cwd or self.settings.get_resolved_data_dir()
        validated_cwd = self.path_guard.validate_path(cwd, must_be_dir=True)

        # 3. Timeout and Output limits
        timeout = request.timeout_seconds or self.settings.command_timeout_seconds
        max_bytes = request.max_output_bytes or self.settings.max_command_output_bytes

        # 4. Prepare sanitized environment
        clean_env = os.environ.copy()
        # Remove dangerous Python injection hooks
        for dangerous_var in ("PYTHONINSPECT", "PYTHONBREAKPOINT", "PYTHONSTARTUP"):
            clean_env.pop(dangerous_var, None)

        cmd_list = [resolved_exe] + list(request.args)
        logger.info("Executing command: %s (cwd=%s, timeout=%ss)", cmd_list, validated_cwd, timeout)
        self.audit_logger.logger.info(
            "AUDIT [execution_started] cmd=%s cwd=%s timeout=%ss",
            [Path(resolved_exe).name] + list(request.args),
            str(validated_cwd),
            timeout,
        )

        timed_out = False
        truncated = False
        raw_stdout = b""
        raw_stderr = b""
        exit_code: Optional[int] = None

        proc = None
        try:
            # Direct process invocation with array and shell=False strictly enforced
            proc = subprocess.Popen(
                cmd_list,
                cwd=str(validated_cwd),
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )

            try:
                raw_stdout, raw_stderr = proc.communicate(timeout=timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                logger.warning("Process %d timed out after %s seconds, terminating...", proc.pid, timeout)
                self.audit_logger.logger.warning(
                    "AUDIT [execution_timeout] pid=%s timeout=%ss",
                    proc.pid,
                    timeout,
                )
                try:
                    proc.terminate()
                    raw_stdout, raw_stderr = proc.communicate(timeout=1.0)
                except (subprocess.TimeoutExpired, Exception):
                    try:
                        proc.kill()
                        raw_stdout, raw_stderr = proc.communicate(timeout=1.0)
                    except Exception:
                        pass
                exit_code = -1

        except Exception as err:
            duration = time.time() - start_time
            logger.error("Process execution error: %s", err)
            return ExecutionResult(
                success=False,
                exit_code=exit_code,
                stdout="",
                stderr=f"Execution error: {err}",
                duration_seconds=round(duration, 2),
                timed_out=False,
                truncated=False,
                cwd=str(validated_cwd),
            )

        duration = time.time() - start_time

        # Truncate output if necessary
        if len(raw_stdout) > max_bytes:
            raw_stdout = raw_stdout[:max_bytes]
            truncated = True

        if len(raw_stderr) > max_bytes:
            raw_stderr = raw_stderr[:max_bytes]
            truncated = True

        stdout_str = raw_stdout.decode("utf-8", errors="replace")
        stderr_str = raw_stderr.decode("utf-8", errors="replace")

        if truncated:
            stdout_str += "\n... [output truncated]"

        success = (exit_code == 0) and not timed_out

        self.audit_logger.logger.info(
            "AUDIT [execution_completed] success=%s exit_code=%s duration=%ss timed_out=%s",
            success,
            exit_code,
            round(duration, 2),
            timed_out,
        )


        return ExecutionResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_seconds=round(duration, 2),
            timed_out=timed_out,
            truncated=truncated,
            cwd=str(validated_cwd),
        )
