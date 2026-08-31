"""Tests for PathGuard security boundary enforcement and path validation."""

from pathlib import Path
import pytest

from app.core.exceptions import ToolValidationError
from app.tools.path_guard import PathGuard


@pytest.fixture
def sandbox_root(tmp_path: Path) -> Path:
    """Fixture providing a primary allowed sandbox root."""
    root = tmp_path / "allowed_root"
    root.mkdir()
    return root


@pytest.fixture
def protected_dir(tmp_path: Path) -> Path:
    """Fixture providing an explicitly protected directory."""
    prot = tmp_path / "protected_dir"
    prot.mkdir()
    return prot


@pytest.fixture
def guard(sandbox_root: Path, protected_dir: Path) -> PathGuard:
    """Fixture providing PathGuard configured with the test sandbox and protected dirs."""
    return PathGuard(
        allowed_roots=[sandbox_root],
        protected_paths=[protected_dir],
    )


def test_allowed_path_accepted(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify that a path residing inside allowed root is validated successfully."""
    target = sandbox_root / "valid_file.txt"
    resolved = guard.validate_path(target)
    assert resolved == target.resolve()
    assert resolved.is_relative_to(sandbox_root.resolve())


def test_relative_path_resolved_against_allowed_root(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify relative paths are resolved relative to the allowed root."""
    resolved = guard.validate_path("subfolder/file.txt")
    assert resolved == (sandbox_root / "subfolder" / "file.txt").resolve()
    assert resolved.is_relative_to(sandbox_root.resolve())


def test_path_outside_allowed_root_rejected(guard: PathGuard, tmp_path: Path) -> None:
    """Verify paths outside allowed root boundaries raise ToolValidationError."""
    outside_file = tmp_path / "outside.txt"
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(outside_file)
    assert "outside allowed directory boundaries" in str(exc_info.value)


def test_path_traversal_double_dot_rejected(guard: PathGuard) -> None:
    """Verify directory traversal attempts via '..' are blocked."""
    traversal_path = "subfolder/../../escaped.txt"
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(traversal_path)
    assert "outside allowed directory boundaries" in str(exc_info.value)


def test_null_byte_injection_rejected(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify null byte injection attempts are detected and rejected."""
    evil_path = f"{sandbox_root}/file.txt\0.jpg"
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(evil_path)
    assert "Null byte" in str(exc_info.value)


def test_empty_or_whitespace_path_rejected(guard: PathGuard) -> None:
    """Verify empty or whitespace-only paths raise ToolValidationError."""
    with pytest.raises(ToolValidationError):
        guard.validate_path("")

    with pytest.raises(ToolValidationError):
        guard.validate_path("   ")


def test_protected_path_rejected(guard: PathGuard, protected_dir: Path) -> None:
    """Verify access to protected paths is rejected."""
    prot_file = protected_dir / "secret.txt"
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(prot_file)
    assert "protected system path" in str(exc_info.value)


def test_allowed_root_deletion_prevented(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify attempting to delete the allowed root itself is strictly blocked."""
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(sandbox_root, for_deletion=True)
    assert "Cannot delete root directory" in str(exc_info.value)


def test_file_must_exist_verification(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify check_exists=True raises if target does not exist."""
    missing = sandbox_root / "nonexistent.txt"
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(missing, check_exists=True)
    assert "Path does not exist" in str(exc_info.value)


def test_file_must_not_exist_verification(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify check_exists=False raises if target already exists."""
    existing = sandbox_root / "exists.txt"
    existing.write_text("content", encoding="utf-8")

    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(existing, check_exists=False)
    assert "Path already exists" in str(exc_info.value)


def test_must_be_file_verification(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify must_be_file raises when path points to a directory."""
    folder = sandbox_root / "a_dir"
    folder.mkdir()

    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(folder, must_be_file=True)
    assert "is not a regular file" in str(exc_info.value)


def test_must_be_dir_verification(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify must_be_dir raises when path points to a file."""
    f = sandbox_root / "a_file.txt"
    f.write_text("hi", encoding="utf-8")

    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(f, must_be_dir=True)
    assert "is not a directory" in str(exc_info.value)


def test_default_allowed_root_is_data_dir(tmp_path: Path) -> None:
    """Verify that when no allowed roots are configured, default access is strictly confined to data/."""
    from app.core.config import Settings
    cfg = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        filesystem_allowed_roots=[],
    )
    roots = cfg.get_resolved_allowed_roots()
    assert len(roots) == 1
    assert roots[0] == (tmp_path / "data").resolve()


def test_mixed_separators_normalized(guard: PathGuard, sandbox_root: Path) -> None:
    """Verify paths with mixed backslashes and forward slashes are normalized cleanly."""
    mixed_path = "subfolder\\nested/deep\\file.txt"
    resolved = guard.validate_path(mixed_path)
    assert resolved == (sandbox_root / "subfolder" / "nested" / "deep" / "file.txt").resolve()
    assert resolved.is_relative_to(sandbox_root.resolve())


def test_ancestor_deletion_containing_protected_path_blocked(tmp_path: Path) -> None:
    """Verify deleting a directory containing a protected child is strictly rejected."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    child_prot = sandbox / "important_config"
    child_prot.mkdir()

    guard = PathGuard(allowed_roots=[sandbox], protected_paths=[child_prot])

    # Deleting sandbox itself or child containing protected path is blocked
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path(sandbox, for_deletion=True)
    assert "Cannot delete" in str(exc_info.value)


def test_symlink_outside_allowed_root_rejected(sandbox_root: Path, tmp_path: Path) -> None:
    """Verify that an existing symlink pointing outside the allowed root is rejected."""
    outside_target = tmp_path / "outside_secret.txt"
    outside_target.write_text("classified", encoding="utf-8")

    link_path = sandbox_root / "sneaky_link.txt"
    try:
        link_path.symlink_to(outside_target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted in this host environment")

    guard = PathGuard(allowed_roots=[sandbox_root], protected_paths=[])
    with pytest.raises(ToolValidationError) as exc_info:
        guard.validate_path("sneaky_link.txt", check_exists=True)
    assert "outside allowed directory boundaries" in str(exc_info.value)

