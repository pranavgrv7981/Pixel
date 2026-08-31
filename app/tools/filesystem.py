"""Secure filesystem tools providing controlled local file and directory operations."""

from datetime import datetime, timezone
import fnmatch
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.core.logging import get_logger
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.path_guard import PathGuard

logger = get_logger("tools.filesystem")


# --- Parameter Schemas ---

class ListDirectoryArgs(BaseModel):
    path: str = Field(default=".", description="Relative or absolute directory path to list")
    limit: Optional[int] = Field(default=None, description="Maximum number of items to return")


class GetFileInfoArgs(BaseModel):
    path: str = Field(description="Path to the file or directory to inspect")


class SearchFilesArgs(BaseModel):
    pattern: str = Field(description="Glob pattern to search for (e.g. '*.txt', 'data*')")
    directory: str = Field(default=".", description="Root directory to begin search")
    recursive: bool = Field(default=True, description="Whether to search recursively")
    limit: Optional[int] = Field(default=None, description="Maximum number of matching files to return")


class ReadTextFileArgs(BaseModel):
    path: str = Field(description="Path to the text file to read")
    max_bytes: Optional[int] = Field(default=None, description="Maximum bytes to read")


class CreateDirectoryArgs(BaseModel):
    path: str = Field(description="Path of the directory to create")
    exist_ok: bool = Field(default=True, description="Whether existing directory is acceptable")


class CreateFileArgs(BaseModel):
    path: str = Field(description="Path of the file to create")
    content: str = Field(default="", description="Initial content to write")
    overwrite: bool = Field(default=False, description="Whether to overwrite if file already exists")


class WriteTextFileArgs(BaseModel):
    path: str = Field(description="Path of the file to write")
    content: str = Field(description="Text content to write")
    append: bool = Field(default=False, description="Whether to append instead of overwriting")


class CopyFileArgs(BaseModel):
    source: str = Field(description="Source file path")
    destination: str = Field(description="Destination file or directory path")
    overwrite: bool = Field(default=False, description="Whether to overwrite destination if it exists")


class MoveFileArgs(BaseModel):
    source: str = Field(description="Source file path to move")
    destination: str = Field(description="Destination file or directory path")
    overwrite: bool = Field(default=False, description="Whether to overwrite destination if it exists")


class RenameFileArgs(BaseModel):
    path: str = Field(description="Path of the file to rename")
    new_name: str = Field(description="New filename (name only, not a path)")


class DeleteFileArgs(BaseModel):
    path: str = Field(description="Path of the file to delete")


class DeleteDirectoryArgs(BaseModel):
    path: str = Field(description="Path of the directory to delete")
    recursive: bool = Field(default=False, description="Must be true to delete non-empty directories")


# --- Base FileSystem Tool ---

class FileSystemTool(Tool):
    """Base class for filesystem tools sharing a PathGuard, settings, and early validation."""

    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        args_model: type[BaseModel],
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(name=name, description=description, risk_level=risk_level, args_model=args_model)
        self.settings: Settings = settings or get_settings()
        self.path_guard: PathGuard = path_guard or PathGuard(settings=self.settings)

    def validate_args(self, args: Any) -> dict[str, Any]:
        """Validate argument structure and enforce path security boundaries before permission check."""
        validated = super().validate_args(args)
        self._validate_paths(validated)
        return validated

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        """Hook for subclass-specific path validation during argument parsing."""
        pass

    @staticmethod
    def _format_error(err: Exception) -> str:
        """Format filesystem exceptions cleanly without leaking raw tracebacks."""
        if isinstance(err, FileNotFoundError):
            return f"File not found: {err.filename or err}"
        elif isinstance(err, FileExistsError):
            return f"File already exists: {err.filename or err}"
        elif isinstance(err, PermissionError):
            return f"Permission denied: {err.filename or err}"
        elif isinstance(err, (IsADirectoryError, NotADirectoryError)):
            return f"Path type error: {err}"
        elif isinstance(err, OSError):
            return f"Filesystem error: {err.strerror or str(err)}"
        return f"Operation failed: {err}"


# --- Read Operations ---

class ListDirectoryTool(FileSystemTool):
    """Lists files and subdirectories within an allowed directory."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="list_directory",
            description="List files and directories in an allowed directory path.",
            risk_level=RiskLevel.READ,
            args_model=ListDirectoryArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated.get("path", "."), check_exists=True, must_be_dir=True)

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(args.get("path", "."), check_exists=True, must_be_dir=True)
        limit = args.get("limit") or self.settings.max_list_results

        items: list[dict[str, Any]] = []
        try:
            for entry in sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                if len(items) >= limit:
                    break
                try:
                    stat = entry.stat()
                    items.append({
                        "name": entry.name,
                        "type": "directory" if entry.is_dir() else "file",
                        "size": stat.st_size if entry.is_file() else None,
                        "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    })
                except (PermissionError, OSError) as item_err:
                    items.append({
                        "name": entry.name,
                        "type": "unknown",
                        "size": None,
                        "error": str(item_err),
                    })

            return ToolResult(
                success=True,
                data={
                    "directory": str(path),
                    "total_listed": len(items),
                    "items": items,
                },
                message=f"Listed {len(items)} items in '{path.name or str(path)}'.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


class GetFileInfoTool(FileSystemTool):
    """Retrieves metadata for an allowed file or directory."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="get_file_info",
            description="Retrieve metadata (size, timestamps, type) for an allowed file or directory.",
            risk_level=RiskLevel.READ,
            args_model=GetFileInfoArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated["path"], check_exists=True)

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(args["path"], check_exists=True)
        try:
            stat = path.stat()
            info = {
                "name": path.name,
                "path": str(path),
                "type": "directory" if path.is_dir() else "file",
                "size_bytes": stat.st_size,
                "created_time": datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
                "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
            return ToolResult(success=True, data=info, message=f"Metadata retrieved for '{path.name}'.")
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


class SearchFilesTool(FileSystemTool):
    """Searches for files matching a pattern inside allowed directories."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="search_files",
            description="Search for files by glob pattern (e.g. '*.txt', 'notes*') within an allowed directory.",
            risk_level=RiskLevel.READ,
            args_model=SearchFilesArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated.get("directory", "."), check_exists=True, must_be_dir=True)

    def _run(self, args: dict[str, Any]) -> ToolResult:
        root_dir = self.path_guard.validate_path(args.get("directory", "."), check_exists=True, must_be_dir=True)
        pattern = args["pattern"]
        recursive = args.get("recursive", True)
        limit = args.get("limit") or self.settings.max_search_results

        matches: list[dict[str, Any]] = []
        try:
            walker = root_dir.rglob("*") if recursive else root_dir.glob("*")
            for p in walker:
                if len(matches) >= limit:
                    break
                try:
                    # Prevent following symlinks outside allowed boundaries
                    resolved_p = p.resolve()
                    if not any(resolved_p == root or resolved_p.is_relative_to(root) for root in self.path_guard.allowed_roots):
                        continue

                    if fnmatch.fnmatch(p.name, pattern):
                        stat = p.stat()
                        matches.append({
                            "name": p.name,
                            "path": str(p),
                            "type": "directory" if p.is_dir() else "file",
                            "size": stat.st_size if p.is_file() else None,
                        })
                except (PermissionError, OSError):
                    continue

            return ToolResult(
                success=True,
                data={
                    "pattern": pattern,
                    "search_root": str(root_dir),
                    "total_matches": len(matches),
                    "matches": matches,
                },
                message=f"Found {len(matches)} matches for pattern '{pattern}'.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


class ReadTextFileTool(FileSystemTool):
    """Safely reads the textual content of a file within byte limits."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="read_text_file",
            description="Read the contents of a text file within allowed directories up to the configured size limit.",
            risk_level=RiskLevel.READ,
            args_model=ReadTextFileArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated["path"], check_exists=True, must_be_file=True)

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(args["path"], check_exists=True, must_be_file=True)
        max_bytes = args.get("max_bytes") or self.settings.max_file_read_bytes

        try:
            file_size = path.stat().st_size
            with open(path, "rb") as f:
                raw = f.read(max_bytes + 1)

            # Check if truncated
            truncated = len(raw) > max_bytes
            data_bytes = raw[:max_bytes] if truncated else raw

            # Detect binary content
            if b"\0" in data_bytes:
                return ToolResult(
                    success=False,
                    error=f"File '{path.name}' appears to be binary and cannot be read as text",
                )

            text_content = data_bytes.decode("utf-8", errors="replace")

            return ToolResult(
                success=True,
                data={
                    "path": str(path),
                    "content": text_content,
                    "truncated": truncated,
                    "bytes_read": len(data_bytes),
                    "total_size": file_size,
                },
                message=f"Read {len(data_bytes)} bytes from '{path.name}'" + (" (truncated)" if truncated else ""),
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


# --- Creation Operations ---

class CreateDirectoryTool(FileSystemTool):
    """Creates a directory within allowed roots."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="create_directory",
            description="Create a new directory in an allowed directory path.",
            risk_level=RiskLevel.LOW,
            args_model=CreateDirectoryArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated["path"])

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(args["path"])
        exist_ok = args.get("exist_ok", True)

        if path.exists() and not exist_ok:
            return ToolResult(success=False, error=f"Directory already exists: '{path.name}'")

        try:
            path.mkdir(parents=True, exist_ok=exist_ok)
            # Post-operation verification
            if not path.is_dir():
                return ToolResult(success=False, error=f"Post-creation verification failed for '{path.name}'")

            return ToolResult(
                success=True,
                data={"path": str(path), "created": True},
                message=f"Directory '{path.name}' created successfully.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


class CreateFileTool(FileSystemTool):
    """Creates a new file without overwriting existing files by default."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="create_file",
            description="Create a new file in an allowed directory path. Fails if file exists unless overwrite=True.",
            risk_level=RiskLevel.LOW,
            args_model=CreateFileArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated["path"])

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(args["path"])
        content: str = args.get("content", "")
        overwrite: bool = args.get("overwrite", False)

        if path.exists() and not overwrite:
            return ToolResult(
                success=False,
                error=f"File already exists: '{path.name}'. Use overwrite=True or write_text_file to replace.",
            )

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > self.settings.max_file_write_bytes:
            return ToolResult(
                success=False,
                error=f"Content size ({len(content_bytes)} bytes) exceeds limit ({self.settings.max_file_write_bytes} bytes)",
            )

        temp_path_str: Optional[str] = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic safe write using a temporary file in the target directory
            temp_fd, temp_path_str = tempfile.mkstemp(dir=path.parent, prefix=".tmp_create_")
            with os.fdopen(temp_fd, "wb") as f:
                f.write(content_bytes)
                f.flush()
                os.fsync(f.fileno())

            os.replace(temp_path_str, str(path))

            # Post-operation verification
            if not path.is_file() or path.stat().st_size != len(content_bytes):
                return ToolResult(success=False, error="Post-creation verification failed")

            return ToolResult(
                success=True,
                data={"path": str(path), "bytes_written": len(content_bytes)},
                message=f"File '{path.name}' created successfully ({len(content_bytes)} bytes).",
            )
        except Exception as err:
            if temp_path_str and os.path.exists(temp_path_str):
                try:
                    os.unlink(temp_path_str)
                except OSError:
                    pass
            return ToolResult(success=False, error=self._format_error(err))


# --- Mutation Operations ---

class WriteTextFileTool(FileSystemTool):
    """Writes or appends content to an allowed file."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="write_text_file",
            description="Write or append text content to an allowed file. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=WriteTextFileArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated["path"])

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(args["path"])
        content: str = args["content"]
        append: bool = args.get("append", False)

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > self.settings.max_file_write_bytes:
            return ToolResult(
                success=False,
                error=f"Write size ({len(content_bytes)} bytes) exceeds limit ({self.settings.max_file_write_bytes} bytes)",
            )

        temp_path_str: Optional[str] = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if append:
                with open(path, "ab") as f:
                    f.write(content_bytes)
                    f.flush()
                    os.fsync(f.fileno())
            else:
                # Atomic write via temporary file
                temp_fd, temp_path_str = tempfile.mkstemp(dir=path.parent, prefix=".tmp_write_")
                with os.fdopen(temp_fd, "wb") as f:
                    f.write(content_bytes)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path_str, str(path))

            # Post-operation verification
            if not path.is_file():
                return ToolResult(success=False, error="Post-write verification failed: file does not exist")

            return ToolResult(
                success=True,
                data={"path": str(path), "bytes_written": len(content_bytes), "mode": "append" if append else "overwrite"},
                message=f"Successfully wrote {len(content_bytes)} bytes to '{path.name}'.",
            )
        except Exception as err:
            if temp_path_str and os.path.exists(temp_path_str):
                try:
                    os.unlink(temp_path_str)
                except OSError:
                    pass
            return ToolResult(success=False, error=self._format_error(err))


class CopyFileTool(FileSystemTool):
    """Copies a file between allowed paths."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="copy_file",
            description="Copy an existing file to a destination within allowed directories.",
            risk_level=RiskLevel.LOW,
            args_model=CopyFileArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated["source"], check_exists=True, must_be_file=True)
        self.path_guard.validate_path(validated["destination"])

    def _run(self, args: dict[str, Any]) -> ToolResult:
        src = self.path_guard.validate_path(args["source"], check_exists=True, must_be_file=True)
        dst_raw = args["destination"]
        overwrite = args.get("overwrite", False)

        dst = self.path_guard.validate_path(dst_raw)
        if dst.is_dir():
            dst = self.path_guard.validate_path(dst / src.name)

        if dst.exists() and not overwrite:
            return ToolResult(success=False, error=f"Destination '{dst.name}' already exists")

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            # Post-operation verification: exists, is file, and size matches source
            if not dst.is_file() or dst.stat().st_size != src.stat().st_size:
                return ToolResult(success=False, error="Post-copy verification failed")

            return ToolResult(
                success=True,
                data={"source": str(src), "destination": str(dst)},
                message=f"Copied '{src.name}' to '{dst.name}' successfully.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


class MoveFileTool(FileSystemTool):
    """Moves a file to a new destination within allowed directories."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="move_file",
            description="Move a file to a destination within allowed directories. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=MoveFileArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(validated["source"], check_exists=True, must_be_file=True)
        self.path_guard.validate_path(validated["destination"])

    def _run(self, args: dict[str, Any]) -> ToolResult:
        src = self.path_guard.validate_path(args["source"], check_exists=True, must_be_file=True)
        dst_raw = args["destination"]
        overwrite = args.get("overwrite", False)

        dst = self.path_guard.validate_path(dst_raw)
        if dst.is_dir():
            dst = self.path_guard.validate_path(dst / src.name)

        if src == dst:
            return ToolResult(success=False, error="Source and destination are identical")

        if dst.exists() and not overwrite:
            return ToolResult(success=False, error=f"Destination '{dst.name}' already exists")

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and overwrite:
                dst.unlink()

            shutil.move(str(src), str(dst))

            # Post-operation verification: destination exists and source is gone
            if not dst.exists() or src.exists():
                return ToolResult(success=False, error="Post-move verification failed")

            return ToolResult(
                success=True,
                data={"source": str(src), "destination": str(dst)},
                message=f"Moved '{src.name}' to '{dst.name}' successfully.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


class RenameFileTool(FileSystemTool):
    """Renames a file within its parent directory."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="rename_file",
            description="Rename a file within its current directory. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=RenameFileArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        src = self.path_guard.validate_path(validated["path"], check_exists=True, must_be_file=True)
        new_name = validated["new_name"].strip()
        if "/" in new_name or "\\" in new_name or new_name in (".", ".."):
            raise ToolValidationError("new_name must be a simple filename, not a path")
        self.path_guard.validate_path(src.parent / new_name)

    def _run(self, args: dict[str, Any]) -> ToolResult:
        src = self.path_guard.validate_path(args["path"], check_exists=True, must_be_file=True)
        new_name = args["new_name"].strip()

        if "/" in new_name or "\\" in new_name or new_name in (".", ".."):
            return ToolResult(success=False, error="new_name must be a simple filename, not a path")

        dst = self.path_guard.validate_path(src.parent / new_name)
        if dst.exists():
            return ToolResult(success=False, error=f"Target file '{new_name}' already exists")

        try:
            src.rename(dst)

            # Post-operation verification
            if not dst.is_file() or src.exists():
                return ToolResult(success=False, error="Post-rename verification failed")

            return ToolResult(
                success=True,
                data={"old_path": str(src), "new_path": str(dst), "new_name": new_name},
                message=f"Renamed '{src.name}' to '{new_name}' successfully.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


# --- Deletion Operations ---

class DeleteFileTool(FileSystemTool):
    """Deletes a single file within allowed directories."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="delete_file",
            description="Permanently delete a file within allowed directories. Requires confirmation.",
            risk_level=RiskLevel.HIGH,
            args_model=DeleteFileArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(
            validated["path"],
            check_exists=True,
            must_be_file=True,
            for_deletion=True,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(
            args["path"],
            check_exists=True,
            must_be_file=True,
            for_deletion=True,
        )

        try:
            path.unlink()

            # Post-operation verification
            if path.exists():
                return ToolResult(success=False, error="Post-deletion verification failed: file still exists")

            return ToolResult(
                success=True,
                data={"path": str(path), "deleted": True},
                message=f"File '{path.name}' deleted successfully.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))


class DeleteDirectoryTool(FileSystemTool):
    """Deletes an allowed directory."""

    def __init__(self, path_guard: Optional[PathGuard] = None, settings: Optional[Settings] = None) -> None:
        super().__init__(
            name="delete_directory",
            description="Delete a directory within allowed boundaries. Requires recursive=True if non-empty. Requires confirmation.",
            risk_level=RiskLevel.HIGH,
            args_model=DeleteDirectoryArgs,
            path_guard=path_guard,
            settings=settings,
        )

    def _validate_paths(self, validated: dict[str, Any]) -> None:
        self.path_guard.validate_path(
            validated["path"],
            check_exists=True,
            must_be_dir=True,
            for_deletion=True,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = self.path_guard.validate_path(
            args["path"],
            check_exists=True,
            must_be_dir=True,
            for_deletion=True,
        )
        recursive = args.get("recursive", False)

        try:
            # Check if directory has contents
            has_contents = any(path.iterdir())
            if has_contents and not recursive:
                return ToolResult(
                    success=False,
                    error=f"Directory '{path.name}' is not empty. Set recursive=True to delete.",
                )

            if recursive:
                shutil.rmtree(path)
            else:
                path.rmdir()

            # Post-operation verification
            if path.exists():
                return ToolResult(success=False, error="Post-deletion verification failed: directory still exists")

            return ToolResult(
                success=True,
                data={"path": str(path), "deleted": True, "recursive": recursive},
                message=f"Directory '{path.name}' deleted successfully.",
            )
        except Exception as err:
            return ToolResult(success=False, error=self._format_error(err))
