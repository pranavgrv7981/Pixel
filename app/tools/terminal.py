"""Controlled terminal and code execution tools operating under strict sandbox boundaries."""

import os
from pathlib import Path
import shutil
import sys
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.core.logging import get_logger
from app.security.execution_policy import ExecutionPolicy, ExecutionRequest
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.path_guard import PathGuard

logger = get_logger("tools.terminal")


# --- Parameter Schemas ---

class GitStatusArgs(BaseModel):
    repo_path: Optional[str] = Field(
        default=None,
        description="Path to git repository directory within allowed roots (defaults to project workspace)",
    )


class GitDiffArgs(BaseModel):
    repo_path: Optional[str] = Field(
        default=None,
        description="Path to git repository directory within allowed roots",
    )
    staged: bool = Field(
        default=False,
        description="If True, shows diff of staged changes (--staged)",
    )


class CompileCArgs(BaseModel):
    source_path: str = Field(
        description="Path to C source file (.c) within allowed roots to compile"
    )
    output_name: Optional[str] = Field(
        default=None,
        description="Optional output binary filename (created in same directory as source file, no path separators)",
    )


class RunPythonArgs(BaseModel):
    script_path: str = Field(
        description="Path to Python script (.py) within allowed roots to execute"
    )
    args: Optional[list[str]] = Field(
        default=None,
        description="Optional command-line arguments to pass to the script",
    )


class RunPytestArgs(BaseModel):
    project_path: Optional[str] = Field(
        default=None,
        description="Path to project directory containing tests within allowed roots",
    )
    test_target: Optional[str] = Field(
        default=None,
        description="Optional specific test file or directory path relative to project",
    )


class RunCProgramArgs(BaseModel):
    executable_path: str = Field(
        description="Path to compiled executable binary within allowed roots"
    )
    args: Optional[list[str]] = Field(
        default=None,
        description="Optional command-line arguments to pass to the program",
    )


# --- Base Terminal Tool ---

class TerminalTool(Tool):
    """Base class for terminal execution tools with PathGuard and ExecutionPolicy."""

    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        args_model: type[BaseModel],
        execution_policy: Optional[ExecutionPolicy] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(name=name, description=description, risk_level=risk_level, args_model=args_model)
        self.settings = settings or get_settings()
        self.path_guard = path_guard or PathGuard(settings=self.settings)
        self.policy = execution_policy or ExecutionPolicy(path_guard=self.path_guard, settings=self.settings)


# --- Tools ---

class GitStatusTool(TerminalTool):
    """Executes read-only git status in an allowed repository."""

    def __init__(
        self,
        execution_policy: Optional[ExecutionPolicy] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="git_status",
            description="Inspect git working tree status for a repository within allowed directories.",
            risk_level=RiskLevel.READ,
            args_model=GitStatusArgs,
            execution_policy=execution_policy,
            path_guard=path_guard,
            settings=settings,
        )

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        raw_path = validated.get("repo_path")
        target_path = raw_path or (
            self.settings.filesystem_allowed_roots[0]
            if self.settings.filesystem_allowed_roots
            else str(self.settings.get_resolved_data_dir())
        )
        resolved = self.path_guard.validate_path(target_path, must_be_dir=True)
        validated["resolved_repo_path"] = resolved
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        repo_dir = args["resolved_repo_path"]
        git_exe = self.settings.git_executable or shutil.which("git")
        if not git_exe:
            return ToolResult(success=False, error="Git executable not found on host system")

        req = ExecutionRequest(
            executable=git_exe,
            args=["status", "--short"],
            cwd=repo_dir,
        )
        res = self.policy.execute(req)

        return ToolResult(
            success=res.success,
            data={
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "timed_out": res.timed_out,
                "truncated": res.truncated,
                "repo_path": str(repo_dir),
            },
            message=f"Git status for {repo_dir.name}:\n{res.stdout.strip() if res.stdout else '(working tree clean)'}",
            error=res.stderr if not res.success else None,
        )


class GitDiffTool(TerminalTool):
    """Executes read-only git diff in an allowed repository."""

    def __init__(
        self,
        execution_policy: Optional[ExecutionPolicy] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="git_diff",
            description="Inspect git diff of changes in a repository within allowed directories.",
            risk_level=RiskLevel.READ,
            args_model=GitDiffArgs,
            execution_policy=execution_policy,
            path_guard=path_guard,
            settings=settings,
        )

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        raw_path = validated.get("repo_path")
        target_path = raw_path or (
            self.settings.filesystem_allowed_roots[0]
            if self.settings.filesystem_allowed_roots
            else str(self.settings.get_resolved_data_dir())
        )
        resolved = self.path_guard.validate_path(target_path, must_be_dir=True)
        validated["resolved_repo_path"] = resolved
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        repo_dir = args["resolved_repo_path"]
        staged = args.get("staged", False)
        git_exe = self.settings.git_executable or shutil.which("git")
        if not git_exe:
            return ToolResult(success=False, error="Git executable not found on host system")

        diff_args = ["diff", "--staged"] if staged else ["diff"]
        req = ExecutionRequest(
            executable=git_exe,
            args=diff_args,
            cwd=repo_dir,
        )
        res = self.policy.execute(req)

        return ToolResult(
            success=res.success,
            data={
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "timed_out": res.timed_out,
                "truncated": res.truncated,
                "repo_path": str(repo_dir),
            },
            message=f"Git diff ({'staged' if staged else 'unstaged'}):\n{res.stdout.strip() if res.stdout else '(no changes)'}",
            error=res.stderr if not res.success else None,
        )


class CompileCProgramTool(TerminalTool):
    """Compiles a C source file to an executable using configured C compiler."""

    def __init__(
        self,
        execution_policy: Optional[ExecutionPolicy] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="compile_c_program",
            description="Compile a C program (.c) within allowed directories. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=CompileCArgs,
            execution_policy=execution_policy,
            path_guard=path_guard,
            settings=settings,
        )

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        source_raw = validated["source_path"]
        resolved_src = self.path_guard.validate_path(source_raw, must_be_file=True)

        if resolved_src.suffix.lower() != ".c":
            raise ToolValidationError(f"Source file '{source_raw}' must have a .c extension")

        output_name = validated.get("output_name")
        if output_name:
            if os.sep in output_name or (os.altsep and os.altsep in output_name) or ".." in output_name:
                raise ToolValidationError("Output name cannot contain path separators or '..'")
        else:
            ext = ".exe" if sys.platform == "win32" else ""
            output_name = f"{resolved_src.stem}{ext}"

        output_path = resolved_src.parent / output_name
        self.path_guard.validate_path(output_path)

        validated["resolved_source"] = resolved_src
        validated["resolved_output"] = output_path
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        source_path: Path = args["resolved_source"]
        output_path: Path = args["resolved_output"]

        compiler = (
            self.settings.compiler_executable
            or shutil.which("gcc")
            or shutil.which("clang")
        )
        if not compiler:
            return ToolResult(success=False, error="C compiler (gcc/clang) not found on host system")

        req = ExecutionRequest(
            executable=compiler,
            args=[str(source_path), "-o", str(output_path)],
            cwd=source_path.parent,
        )
        res = self.policy.execute(req)

        # Post-operation verification: verify compiled output was generated
        if res.success and not output_path.is_file():
            return ToolResult(
                success=False,
                data={"stdout": res.stdout, "stderr": res.stderr},
                error=f"Compilation reported success but output binary '{output_path.name}' was not found",
            )

        return ToolResult(
            success=res.success,
            data={
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "output_binary": str(output_path),
                "duration_seconds": res.duration_seconds,
            },
            message=f"Compiled '{source_path.name}' to '{output_path.name}'." if res.success else "Compilation failed.",
            error=res.stderr if not res.success else None,
        )


class RunPythonFileTool(TerminalTool):
    """Executes a Python script located within allowed filesystem boundaries."""

    def __init__(
        self,
        execution_policy: Optional[ExecutionPolicy] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="run_python_file",
            description="Execute a Python script (.py) located within allowed directories. Requires confirmation.",
            risk_level=RiskLevel.HIGH,
            args_model=RunPythonArgs,
            execution_policy=execution_policy,
            path_guard=path_guard,
            settings=settings,
        )

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        script_raw = validated["script_path"]
        resolved_script = self.path_guard.validate_path(script_raw, must_be_file=True)

        if resolved_script.suffix.lower() != ".py":
            raise ToolValidationError(f"Target script '{script_raw}' must have a .py extension")

        validated["resolved_script"] = resolved_script
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        script_path: Path = args["resolved_script"]
        script_args = args.get("args") or []

        py_exe = self.settings.python_executable or sys.executable

        req = ExecutionRequest(
            executable=py_exe,
            args=[str(script_path)] + list(script_args),
            cwd=script_path.parent,
        )
        res = self.policy.execute(req)

        return ToolResult(
            success=res.success,
            data={
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "timed_out": res.timed_out,
                "truncated": res.truncated,
                "duration_seconds": res.duration_seconds,
                "script": str(script_path),
            },
            message=f"Executed '{script_path.name}' (exit code: {res.exit_code}):\n{res.stdout.strip() if res.stdout else '(no stdout)'}",
            error=res.stderr if not res.success else None,
        )


class RunPytestTool(TerminalTool):
    """Executes pytest against an allowed project directory."""

    def __init__(
        self,
        execution_policy: Optional[ExecutionPolicy] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="run_pytest",
            description="Run pytest suite for a project within allowed directories. Requires confirmation.",
            risk_level=RiskLevel.HIGH,
            args_model=RunPytestArgs,
            execution_policy=execution_policy,
            path_guard=path_guard,
            settings=settings,
        )

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        project_raw = validated.get("project_path")
        target_path = project_raw or (
            self.settings.filesystem_allowed_roots[0]
            if self.settings.filesystem_allowed_roots
            else str(self.settings.get_resolved_data_dir())
        )
        resolved_proj = self.path_guard.validate_path(target_path, must_be_dir=True)

        target_raw = validated.get("test_target")
        if target_raw:
            if ".." in target_raw:
                raise ToolValidationError("test_target cannot contain traversal '..'")
            resolved_target = self.path_guard.validate_path(resolved_proj / target_raw)
            validated["resolved_target"] = str(resolved_target.relative_to(resolved_proj))

        validated["resolved_project"] = resolved_proj
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        project_dir: Path = args["resolved_project"]
        target = args.get("resolved_target")

        py_exe = self.settings.python_executable or sys.executable
        cmd_args = ["-m", "pytest"]
        if target:
            cmd_args.append(target)

        req = ExecutionRequest(
            executable=py_exe,
            args=cmd_args,
            cwd=project_dir,
        )
        res = self.policy.execute(req)

        return ToolResult(
            success=res.success,
            data={
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "timed_out": res.timed_out,
                "truncated": res.truncated,
                "duration_seconds": res.duration_seconds,
                "project": str(project_dir),
            },
            message=f"Pytest finished with exit code {res.exit_code}:\n{res.stdout.strip() if res.stdout else res.stderr.strip()}",
            error=res.stderr if not res.success else None,
        )


class RunCProgramTool(TerminalTool):
    """Executes a compiled C binary strictly originating within allowed roots."""

    def __init__(
        self,
        execution_policy: Optional[ExecutionPolicy] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="run_c_program",
            description="Run a compiled binary originating from allowed directories. Requires confirmation.",
            risk_level=RiskLevel.HIGH,
            args_model=RunCProgramArgs,
            execution_policy=execution_policy,
            path_guard=path_guard,
            settings=settings,
        )

    def validate_args(self, args: Any) -> dict[str, Any]:
        validated = super().validate_args(args)
        exe_raw = validated["executable_path"]
        resolved_exe = self.path_guard.validate_path(exe_raw, must_be_file=True)

        validated["resolved_executable"] = resolved_exe
        return validated

    def _run(self, args: dict[str, Any]) -> ToolResult:
        exe_path: Path = args["resolved_executable"]
        prog_args = args.get("args") or []

        req = ExecutionRequest(
            executable=str(exe_path),
            args=list(prog_args),
            cwd=exe_path.parent,
        )
        res = self.policy.execute(req)

        return ToolResult(
            success=res.success,
            data={
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "timed_out": res.timed_out,
                "truncated": res.truncated,
                "duration_seconds": res.duration_seconds,
                "executable": str(exe_path),
            },
            message=f"Program executed (exit code: {res.exit_code}):\n{res.stdout.strip() if res.stdout else '(no stdout)'}",
            error=res.stderr if not res.success else None,
        )
