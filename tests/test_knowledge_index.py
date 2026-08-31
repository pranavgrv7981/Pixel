"""Tests for SQLite KnowledgeDatabase index operations, incremental updates, and cascading deletion."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.core.config import Settings
from app.knowledge.index import KnowledgeDatabase
from app.knowledge.models import DocumentChunk, DocumentMetadata


@pytest.fixture
def temp_knowledge_db(tmp_path: Path) -> KnowledgeDatabase:
    db_file = tmp_path / "test_knowledge.db"
    settings = Settings(knowledge_database_path=str(db_file))
    db = KnowledgeDatabase(db_path=db_file, settings=settings, embedding_dimensions=4)
    db.initialize()
    return db


def test_knowledge_database_initialization_and_schema(temp_knowledge_db: KnowledgeDatabase) -> None:
    assert temp_knowledge_db.db_path.exists()
    assert temp_knowledge_db.check_integrity() is True

    with temp_knowledge_db.transaction() as conn:
        row = conn.execute("SELECT version, embedding_model, embedding_dimensions FROM knowledge_schema_version;").fetchone()
        assert row is not None
        assert row["version"] == 1
        assert row["embedding_dimensions"] == 4


def test_add_document_and_chunks(temp_knowledge_db: KnowledgeDatabase) -> None:
    doc = DocumentMetadata(
        document_id="doc-1",
        source_path="/data/file.txt",
        file_name="file.txt",
        file_type="txt",
        file_size=120,
        modified_time=100.0,
        content_hash="hash123",
        indexed_at=datetime.now(timezone.utc),
    )
    chunks = [
        DocumentChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            text="First chunk of content",
            source_path="/data/file.txt",
            file_name="file.txt",
            file_type="txt",
            chunk_index=0,
            embedding=[0.1, 0.2, 0.3, 0.4],
        ),
        DocumentChunk(
            chunk_id="chunk-2",
            document_id="doc-1",
            text="Second chunk of content",
            source_path="/data/file.txt",
            file_name="file.txt",
            file_type="txt",
            chunk_index=1,
            embedding=[0.5, 0.6, 0.7, 0.8],
        ),
    ]

    temp_knowledge_db.add_document_and_chunks(doc, chunks)

    assert temp_knowledge_db.get_document_count() == 1
    assert temp_knowledge_db.get_chunk_count() == 2

    fetched_doc = temp_knowledge_db.get_document_by_path("/data/file.txt")
    assert fetched_doc is not None
    assert fetched_doc.content_hash == "hash123"

    fetched_chunks = temp_knowledge_db.get_all_chunks()
    assert len(fetched_chunks) == 2
    assert fetched_chunks[0].embedding == pytest.approx([0.1, 0.2, 0.3, 0.4], abs=1e-5)


def test_cascading_document_deletion(temp_knowledge_db: KnowledgeDatabase) -> None:
    doc = DocumentMetadata(
        document_id="doc-delete",
        source_path="/data/delete_me.txt",
        file_name="delete_me.txt",
        file_type="txt",
        file_size=10,
        modified_time=100.0,
        content_hash="h1",
        indexed_at=datetime.now(timezone.utc),
    )
    chunks = [
        DocumentChunk(
            chunk_id="c-del-1",
            document_id="doc-delete",
            text="Temporary chunk",
            source_path="/data/delete_me.txt",
            file_name="delete_me.txt",
            file_type="txt",
            chunk_index=0,
            embedding=[0.0, 0.0, 0.0, 0.0],
        )
    ]
    temp_knowledge_db.add_document_and_chunks(doc, chunks)
    assert temp_knowledge_db.get_chunk_count() == 1

    deleted = temp_knowledge_db.remove_document("doc-delete")
    assert deleted is True
    assert temp_knowledge_db.get_document_count() == 0
    # Cascade delete verification
    assert temp_knowledge_db.get_chunk_count() == 0


def test_cleanup_stale_documents(tmp_path: Path, temp_knowledge_db: KnowledgeDatabase) -> None:
    # Create real file on disk
    real_file = tmp_path / "real.txt"
    real_file.write_text("Hello real", encoding="utf-8")

    doc_real = DocumentMetadata(
        document_id="doc-real",
        source_path=str(real_file.resolve()),
        file_name="real.txt",
        file_type="txt",
        file_size=10,
        modified_time=100.0,
        content_hash="hr",
        indexed_at=datetime.now(timezone.utc),
    )
    temp_knowledge_db.add_document_and_chunks(doc_real, [])

    # Create record for non-existent file
    doc_ghost = DocumentMetadata(
        document_id="doc-ghost",
        source_path=str((tmp_path / "ghost.txt").resolve()),
        file_name="ghost.txt",
        file_type="txt",
        file_size=10,
        modified_time=100.0,
        content_hash="hg",
        indexed_at=datetime.now(timezone.utc),
    )
    temp_knowledge_db.add_document_and_chunks(doc_ghost, [])

    assert temp_knowledge_db.get_document_count() == 2
    cleaned = temp_knowledge_db.cleanup_stale_documents()
    assert len(cleaned) == 1
    assert "ghost.txt" in cleaned[0]
    assert temp_knowledge_db.get_document_count() == 1
