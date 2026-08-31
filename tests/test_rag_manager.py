"""Tests for KnowledgeManager high-level indexing, directory traversal, and incremental skipping."""

from pathlib import Path
import pytest

from app.core.config import Settings
from app.knowledge.manager import KnowledgeManager
from app.tools.path_guard import PathGuard


@pytest.fixture
def manager_env(tmp_path: Path) -> tuple[KnowledgeManager, Path]:
    allowed_dir = tmp_path / "allowed_docs"
    allowed_dir.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "test_km.db"

    settings = Settings(
        filesystem_allowed_roots=[str(allowed_dir)],
        knowledge_database_path=str(db_file),
        max_indexed_files_per_operation=5,
        max_document_size_bytes=10000,
    )
    guard = PathGuard(settings=settings)
    km = KnowledgeManager(settings=settings, path_guard=guard)
    km.initialize()

    return km, allowed_dir


def test_index_single_file_and_incremental_skip(manager_env: tuple[KnowledgeManager, Path]) -> None:
    km, allowed_dir = manager_env
    doc_path = allowed_dir / "notes.txt"
    doc_path.write_text("Notes on dynamic programming and memoization.", encoding="utf-8")

    # 1. First index
    res1 = km.index_file(doc_path)
    assert res1.documents_indexed == 1
    assert res1.documents_skipped == 0
    assert res1.chunks_created >= 1

    # 2. Re-indexing identical file without changes skips re-embedding
    res2 = km.index_file(doc_path)
    assert res2.documents_indexed == 0
    assert res2.documents_skipped == 1

    # 3. Modify content -> re-indexes with new hash
    doc_path.write_text("Updated notes with Tabulation details.", encoding="utf-8")
    res3 = km.index_file(doc_path)
    assert res3.documents_indexed == 1
    assert res3.documents_skipped == 0


def test_index_directory_with_limits_and_isolation(manager_env: tuple[KnowledgeManager, Path]) -> None:
    km, allowed_dir = manager_env

    # Create 3 valid files and 1 invalid extension
    (allowed_dir / "f1.txt").write_text("Content 1", encoding="utf-8")
    (allowed_dir / "f2.md").write_text("# Heading\nContent 2", encoding="utf-8")
    (allowed_dir / "f3.py").write_text("x = 42", encoding="utf-8")
    (allowed_dir / "f4.exe").write_bytes(b"MZ12345")

    res = km.index_directory(allowed_dir)
    assert res.documents_indexed == 3
    # f4.exe was not supported so it didn't crash the operation
    assert res.documents_failed == 0

    docs = km.list_documents()
    assert len(docs) == 3


def test_remove_file_from_index(manager_env: tuple[KnowledgeManager, Path]) -> None:
    km, allowed_dir = manager_env
    doc_path = allowed_dir / "to_remove.txt"
    doc_path.write_text("Temporary text", encoding="utf-8")

    km.index_file(doc_path)
    assert len(km.list_documents()) == 1

    removed = km.remove_file(doc_path)
    assert removed is True
    assert len(km.list_documents()) == 0
