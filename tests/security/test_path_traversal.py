"""Adversarial tests for filesystem boundary defense and path traversal tricks."""

import pytest
from pathlib import Path
from app.core.exceptions import ToolValidationError
from app.tools.path_guard import PathGuard


@pytest.fixture
def path_guard(tmp_path: Path) -> PathGuard:
    allowed = [tmp_path / "allowed"]
    allowed[0].mkdir(parents=True, exist_ok=True)
    protected = [tmp_path / "protected"]
    protected[0].mkdir(parents=True, exist_ok=True)
    return PathGuard(allowed_roots=allowed, protected_paths=protected)


def test_path_traversal_dot_dot_escape(path_guard: PathGuard) -> None:
    escapes = [
        "../outside.txt",
        "../../etc/passwd",
        "..\\..\\Windows\\System32",
        "allowed/../../outside.txt",
    ]
    for esc in escapes:
        with pytest.raises(ToolValidationError) as exc:
            path_guard.validate_path(esc)
        assert "outside allowed" in str(exc.value).lower() or "boundary" in str(exc.value).lower()


def test_null_byte_injection_blocked(path_guard: PathGuard) -> None:
    with pytest.raises(ToolValidationError) as exc:
        path_guard.validate_path("allowed/test.txt\0.exe")
    assert "null byte" in str(exc.value).lower()


def test_unc_and_device_paths_blocked(path_guard: PathGuard) -> None:
    unc_paths = [
        r"\\.\PhysicalDrive0",
        r"\\?\C:\Windows",
        r"\\192.168.1.1\share",
    ]
    for unc in unc_paths:
        with pytest.raises(ToolValidationError) as exc:
            path_guard.validate_path(unc)
        assert "unc" in str(exc.value).lower() or "device" in str(exc.value).lower()


def test_reserved_windows_device_names_blocked(path_guard: PathGuard) -> None:
    reserved = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
    for res in reserved:
        with pytest.raises(ToolValidationError) as exc:
            path_guard.validate_path(res)
        assert "reserved device" in str(exc.value).lower()


def test_root_directory_deletion_denied(path_guard: PathGuard) -> None:
    root = path_guard.allowed_roots[0]
    with pytest.raises(ToolValidationError) as exc:
        path_guard.validate_path(str(root), for_deletion=True)
    assert "cannot delete root directory" in str(exc.value).lower()
