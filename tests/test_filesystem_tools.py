"""Tests for the 12 filesystem tools in app/tools/filesystem.py."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.tools.filesystem import (
    CopyFileTool,
    CreateDirectoryTool,
    CreateFileTool,
    DeleteDirectoryTool,
    DeleteFileTool,
    GetFileInfoTool,
    ListDirectoryTool,
    MoveFileTool,
    ReadTextFileTool,
    RenameFileTool,
    SearchFilesTool,
    WriteTextFileTool,
)
from app.tools.path_guard import PathGuard


@pytest.fixture
def sandbox(tmp_path: Path) -> tuple[Path, PathGuard, Settings]:
    """Provide an isolated sandbox directory, PathGuard, and Settings."""
    root = tmp_path / "sandbox"
    root.mkdir()
    settings = Settings(
        project_root=tmp_path,
        data_dir=root,
        logs_dir=tmp_path / "logs",
        filesystem_allowed_roots=[str(root)],
        max_file_read_bytes=1024,
        max_file_write_bytes=1024,
    )
    guard = PathGuard(settings=settings, allowed_roots=[root], protected_paths=[])
    return root, guard, settings


def test_create_and_list_directory(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify directory creation and listing."""
    root, guard, settings = sandbox
    mkdir_tool = CreateDirectoryTool(path_guard=guard, settings=settings)
    list_tool = ListDirectoryTool(path_guard=guard, settings=settings)

    # Create directory
    res_mk = mkdir_tool.execute({"path": "projects"})
    assert res_mk.success is True
    assert (root / "projects").is_dir()

    # Create dummy file inside
    (root / "projects" / "file1.txt").write_text("hello", encoding="utf-8")

    # List directory
    res_list = list_tool.execute({"path": "projects"})
    assert res_list.success is True
    assert res_list.data["total_listed"] == 1
    item = res_list.data["items"][0]
    assert item["name"] == "file1.txt"
    assert item["type"] == "file"


def test_create_file_and_prevent_accidental_overwrite(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify file creation prevents overwrite unless explicitly requested."""
    root, guard, settings = sandbox
    create_tool = CreateFileTool(path_guard=guard, settings=settings)

    # Create new file
    res1 = create_tool.execute({"path": "note.txt", "content": "Initial notes"})
    assert res1.success is True
    assert (root / "note.txt").read_text(encoding="utf-8") == "Initial notes"

    # Attempt to create without overwrite -> error
    res2 = create_tool.execute({"path": "note.txt", "content": "New content"})
    assert res2.success is False
    assert "already exists" in res2.error

    # Create with overwrite -> succeeds
    res3 = create_tool.execute({"path": "note.txt", "content": "Overwritten content", "overwrite": True})
    assert res3.success is True
    assert (root / "note.txt").read_text(encoding="utf-8") == "Overwritten content"


def test_read_text_file_and_truncation(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify text file reading, byte limits, and truncation."""
    root, guard, settings = sandbox
    read_tool = ReadTextFileTool(path_guard=guard, settings=settings)

    # Read normal text
    file_path = root / "sample.txt"
    file_path.write_text("Hello World!", encoding="utf-8")

    res = read_tool.execute({"path": "sample.txt"})
    assert res.success is True
    assert res.data["content"] == "Hello World!"
    assert res.data["truncated"] is False

    # Read with truncation limit
    res_trunc = read_tool.execute({"path": "sample.txt", "max_bytes": 5})
    assert res_trunc.success is True
    assert res_trunc.data["content"] == "Hello"
    assert res_trunc.data["truncated"] is True


def test_read_binary_file_fails_safely(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify reading a binary file does not crash and safely returns error."""
    root, guard, settings = sandbox
    read_tool = ReadTextFileTool(path_guard=guard, settings=settings)

    bin_path = root / "binary.bin"
    bin_path.write_bytes(b"\x00\x01\x02\x03\x00\xff")

    res = read_tool.execute({"path": "binary.bin"})
    assert res.success is False
    assert "appears to be binary" in res.error


def test_get_file_info(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify file metadata retrieval."""
    root, guard, settings = sandbox
    info_tool = GetFileInfoTool(path_guard=guard, settings=settings)

    f = root / "doc.txt"
    f.write_text("Documentation", encoding="utf-8")

    res = info_tool.execute({"path": "doc.txt"})
    assert res.success is True
    assert res.data["name"] == "doc.txt"
    assert res.data["type"] == "file"
    assert res.data["size_bytes"] == len("Documentation")


def test_search_files(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify search_files finds matching patterns recursively."""
    root, guard, settings = sandbox
    search_tool = SearchFilesTool(path_guard=guard, settings=settings)

    sub = root / "sub"
    sub.mkdir()
    (root / "a.py").write_text("# py", encoding="utf-8")
    (root / "b.txt").write_text("txt", encoding="utf-8")
    (sub / "c.py").write_text("# py2", encoding="utf-8")

    res = search_tool.execute({"pattern": "*.py", "directory": "."})
    assert res.success is True
    assert res.data["total_matches"] == 2
    matched_names = [m["name"] for m in res.data["matches"]]
    assert "a.py" in matched_names
    assert "c.py" in matched_names


def test_write_text_file_overwrite_and_append(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify write_text_file handles both overwrite and append modes."""
    root, guard, settings = sandbox
    write_tool = WriteTextFileTool(path_guard=guard, settings=settings)

    # Initial write
    res1 = write_tool.execute({"path": "log.txt", "content": "Line 1\n"})
    assert res1.success is True
    assert (root / "log.txt").read_text(encoding="utf-8") == "Line 1\n"

    # Append write
    res2 = write_tool.execute({"path": "log.txt", "content": "Line 2\n", "append": True})
    assert res2.success is True
    assert (root / "log.txt").read_text(encoding="utf-8") == "Line 1\nLine 2\n"


def test_write_text_file_size_limit_enforced(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify write size limit is strictly enforced."""
    root, guard, settings = sandbox
    write_tool = WriteTextFileTool(path_guard=guard, settings=settings)

    huge_content = "X" * 2048  # Exceeds max_file_write_bytes (1024)
    res = write_tool.execute({"path": "huge.txt", "content": huge_content})
    assert res.success is False
    assert "exceeds limit" in res.error
    assert not (root / "huge.txt").exists()


def test_copy_file(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify copy_file duplicates file without removing source."""
    root, guard, settings = sandbox
    copy_tool = CopyFileTool(path_guard=guard, settings=settings)

    src = root / "orig.txt"
    src.write_text("Original text", encoding="utf-8")

    res = copy_tool.execute({"source": "orig.txt", "destination": "copied.txt"})
    assert res.success is True
    assert src.exists()
    assert (root / "copied.txt").exists()
    assert (root / "copied.txt").read_text(encoding="utf-8") == "Original text"


def test_move_file(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify move_file relocates file and deletes source."""
    root, guard, settings = sandbox
    move_tool = MoveFileTool(path_guard=guard, settings=settings)

    src = root / "to_move.txt"
    src.write_text("Moving text", encoding="utf-8")

    res = move_tool.execute({"source": "to_move.txt", "destination": "moved.txt"})
    assert res.success is True
    assert not src.exists()
    assert (root / "moved.txt").exists()
    assert (root / "moved.txt").read_text(encoding="utf-8") == "Moving text"


def test_rename_file(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify rename_file renames a file and prevents path separator injection."""
    root, guard, settings = sandbox
    rename_tool = RenameFileTool(path_guard=guard, settings=settings)

    src = root / "old.txt"
    src.write_text("Renaming text", encoding="utf-8")

    # Path traversal rejection in new_name
    res_bad = rename_tool.execute({"path": "old.txt", "new_name": "../escaped.txt"})
    assert res_bad.success is False
    assert "must be a simple filename" in res_bad.error

    # Valid rename
    res_good = rename_tool.execute({"path": "old.txt", "new_name": "new.txt"})
    assert res_good.success is True
    assert not src.exists()
    assert (root / "new.txt").exists()


def test_delete_file(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify delete_file deletes files and rejects directory targets."""
    root, guard, settings = sandbox
    delete_file_tool = DeleteFileTool(path_guard=guard, settings=settings)

    f = root / "delete_me.txt"
    f.write_text("bye", encoding="utf-8")

    res = delete_file_tool.execute({"path": "delete_me.txt"})
    assert res.success is True
    assert not f.exists()

    # Reject trying to delete directory
    d = root / "a_dir"
    d.mkdir()
    res_dir = delete_file_tool.execute({"path": "a_dir"})
    assert res_dir.success is False
    assert "is not a regular file" in res_dir.error
    assert d.exists()


def test_delete_directory(sandbox: tuple[Path, PathGuard, Settings]) -> None:
    """Verify delete_directory handles empty and recursive deletions."""
    root, guard, settings = sandbox
    delete_dir_tool = DeleteDirectoryTool(path_guard=guard, settings=settings)

    # Empty directory deletion
    d1 = root / "empty_dir"
    d1.mkdir()
    res1 = delete_dir_tool.execute({"path": "empty_dir"})
    assert res1.success is True
    assert not d1.exists()

    # Non-empty directory without recursive=True -> error
    d2 = root / "full_dir"
    d2.mkdir()
    (d2 / "file.txt").write_text("data", encoding="utf-8")

    res2 = delete_dir_tool.execute({"path": "full_dir", "recursive": False})
    assert res2.success is False
    assert "not empty" in res2.error
    assert d2.exists()

    # Non-empty directory with recursive=True -> succeeds
    res3 = delete_dir_tool.execute({"path": "full_dir", "recursive": True})
    assert res3.success is True
    assert not d2.exists()
