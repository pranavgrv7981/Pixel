"""Central path validation and boundary defense layer for filesystem tools."""

import os
from pathlib import Path
from typing import Optional, Union

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.core.logging import get_logger

logger = get_logger("tools.path_guard")


class PathGuard:
    """Validates and sanitizes file paths to enforce containment within allowed roots."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        allowed_roots: Optional[list[Path]] = None,
        protected_paths: Optional[list[Path]] = None,
    ) -> None:
        cfg = settings or get_settings()
        self.allowed_roots: list[Path] = (
            [r.resolve() for r in allowed_roots]
            if allowed_roots is not None
            else cfg.get_resolved_allowed_roots()
        )
        self.protected_paths: list[Path] = (
            [p.resolve() for p in protected_paths]
            if protected_paths is not None
            else cfg.get_resolved_protected_paths()
        )

    def validate_path(
        self,
        path_input: Union[str, Path],
        check_exists: Optional[bool] = None,
        must_be_file: bool = False,
        must_be_dir: bool = False,
        for_deletion: bool = False,
    ) -> Path:
        """Sanitize and validate an input path against security boundaries.

        Args:
            path_input: The raw path string or Path from the LLM/user.
            check_exists: If True, path must exist; if False, path must not exist.
            must_be_file: If True, existing path must be a regular file.
            must_be_dir: If True, existing path must be a directory.
            for_deletion: If True, asserts the path is not an allowed root directory or parent of protected paths.

        Returns:
            Resolved absolute Path guaranteed to reside inside allowed roots.

        Raises:
            ToolValidationError: If path is malformed, escapes allowed roots, or targets protected resources.
        """
        if path_input is None:
            raise ToolValidationError("Path cannot be empty or None")

        raw_str = str(path_input).strip()
        if not raw_str:
            raise ToolValidationError("Path cannot be empty or whitespace-only")

        # Explicitly reject null bytes to prevent string truncation / bypass attacks
        if "\0" in raw_str:
            raise ToolValidationError("Null byte injection detected in path")

        # Reject Windows raw device / UNC namespaces
        norm_prefix = raw_str.replace("/", "\\")
        if norm_prefix.startswith(("\\\\.\\", "\\\\?\\", "\\\\")):
            raise ToolValidationError("UNC and raw device paths are prohibited")

        # Reject reserved Windows device names
        stem_upper = Path(raw_str).stem.upper()
        if stem_upper in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}:
            raise ToolValidationError(f"Access to Windows reserved device name '{stem_upper}' is prohibited")

        path_obj = Path(raw_str)

        # Resolve path relative to the primary allowed root if relative
        if not path_obj.is_absolute():
            base_root = self.allowed_roots[0] if self.allowed_roots else Path.cwd().resolve()
            resolved = (base_root / path_obj).resolve()
        else:
            resolved = path_obj.resolve()

        # 1. Verify path is not protected, nor an ancestor of a protected path during deletion
        for protected in self.protected_paths:
            try:
                resolved_prot = protected.resolve()
                if resolved == resolved_prot or resolved.is_relative_to(resolved_prot):
                    logger.warning("Access denied: path '%s' targets protected location '%s'", raw_str, protected)
                    raise ToolValidationError(f"Access to protected system path '{raw_str}' is prohibited")
                if for_deletion and resolved_prot.is_relative_to(resolved):
                    logger.warning("Deletion denied: deleting '%s' would destroy protected path '%s'", raw_str, protected)
                    raise ToolValidationError(f"Cannot delete path '{raw_str}' because it contains protected path '{protected}'")
            except (ValueError, TypeError):
                continue

        # 2. Check existing parent for non-existent target to prevent symlink/junction escape
        if not resolved.exists():
            parent_resolved = resolved.parent.resolve()
            is_parent_contained = any(
                parent_resolved == root or parent_resolved.is_relative_to(root)
                for root in self.allowed_roots
            )
            if not is_parent_contained:
                logger.warning("Access denied: parent of '%s' resolves outside allowed roots", raw_str)
                raise ToolValidationError(f"Path '{raw_str}' resolves outside allowed directory boundaries")

        # 3. Verify containment within allowed roots

        is_contained = False
        for root in self.allowed_roots:
            resolved_root = root.resolve()
            try:
                if resolved == resolved_root or resolved.is_relative_to(resolved_root):
                    is_contained = True
                    break
            except (ValueError, TypeError):
                continue

        if not is_contained:
            logger.warning("Access denied: path '%s' resolves outside allowed roots", raw_str)
            raise ToolValidationError(f"Path '{raw_str}' is outside allowed directory boundaries")

        # 3. Root directory deletion guard
        if for_deletion:
            for root in self.allowed_roots:
                try:
                    if resolved == root.resolve():
                        logger.warning("Deletion denied: cannot delete allowed root '%s'", root)
                        raise ToolValidationError(f"Cannot delete root directory '{raw_str}'")
                except (ValueError, TypeError):
                    continue

        # 4. Optional existence and file-type verification
        if check_exists is True and not resolved.exists():
            raise ToolValidationError(f"Path does not exist: '{raw_str}'")
        elif check_exists is False and resolved.exists():
            raise ToolValidationError(f"Path already exists: '{raw_str}'")

        if must_be_file and resolved.exists() and not resolved.is_file():
            raise ToolValidationError(f"Path is not a regular file: '{raw_str}'")

        if must_be_dir and resolved.exists() and not resolved.is_dir():
            raise ToolValidationError(f"Path is not a directory: '{raw_str}'")

        return resolved
