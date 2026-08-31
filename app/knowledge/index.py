"""SQLite-based local knowledge index and vector storage."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import struct
from typing import Generator, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolExecutionError
from app.core.logging import get_logger
from app.knowledge.models import DocumentChunk, DocumentMetadata


class KnowledgeIndexError(ToolExecutionError):
    """Raised when a knowledge database or indexing operation fails."""


def serialize_vector(vector: list[float]) -> bytes:
    """Serialize a list of floats into binary float32 bytes."""
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_vector(blob: bytes) -> list[float]:
    """Deserialize binary float32 bytes into a list of floats."""
    num_floats = len(blob) // 4
    return list(struct.unpack(f"{num_floats}f", blob))


class KnowledgeDatabase:
    """Manages SQLite storage for indexed documents, chunks, and dense embeddings."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        settings: Optional[Settings] = None,
        embedding_model: str = "local-hash-384",
        embedding_dimensions: int = 384,
    ) -> None:
        self.settings = settings or get_settings()
        self.db_path = db_path or self.settings.get_resolved_knowledge_db_path()
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.logger = get_logger("knowledge.index")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic SQLite transaction."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=15.0,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create knowledge database schema idempotently."""
        self.logger.info("Initializing knowledge database at '%s'...", self.db_path)
        with self.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_schema_version (
                    version INTEGER PRIMARY KEY,
                    embedding_model TEXT NOT NULL,
                    embedding_dimensions INTEGER NOT NULL,
                    applied_at TEXT NOT NULL
                );
                """
            )

            # Check existing version and embedding dimensions compatibility
            row = conn.execute("SELECT version, embedding_model, embedding_dimensions FROM knowledge_schema_version ORDER BY version DESC LIMIT 1;").fetchone()
            if row is not None:
                stored_dims = row["embedding_dimensions"]
                if stored_dims != self.embedding_dimensions:
                    self.logger.warning(
                        "Embedding dimensions changed from %d to %d. Reindexing may be required.",
                        stored_dims,
                        self.embedding_dimensions,
                    )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_documents (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    modified_time REAL NOT NULL,
                    content_hash TEXT NOT NULL,
                    indexed_at TEXT NOT NULL
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    page_number INTEGER,
                    heading TEXT,
                    embedding_blob BLOB NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES indexed_documents(id) ON DELETE CASCADE
                );
                """
            )

            # Performance indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(document_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON document_chunks(source_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_type ON document_chunks(file_type);")

            # Record schema version 1 if not present
            if row is None:
                now_utc = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO knowledge_schema_version (version, embedding_model, embedding_dimensions, applied_at) VALUES (1, ?, ?, ?);",
                    (self.embedding_model, self.embedding_dimensions, now_utc),
                )
                self.logger.info("Knowledge schema version 1 applied successfully.")

    def check_integrity(self) -> bool:
        """Run SQLite integrity check to verify database health."""
        if not self.db_path.exists():
            return False
        try:
            with self.transaction() as conn:
                res = conn.execute("PRAGMA integrity_check;").fetchone()
                return res is not None and res[0] == "ok"
        except Exception as err:
            self.logger.error("Knowledge database integrity check failed: %s", err)
            return False

    def get_document_by_path(self, source_path: str) -> Optional[DocumentMetadata]:
        """Fetch metadata for a document by its source path."""
        norm_path = str(Path(source_path).resolve())
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM indexed_documents WHERE source_path = ?;",
                (norm_path,),
            ).fetchone()
            if row is None:
                return None
            return DocumentMetadata(
                document_id=row["id"],
                source_path=row["source_path"],
                file_name=row["file_name"],
                file_type=row["file_type"],
                file_size=row["file_size"],
                modified_time=row["modified_time"],
                content_hash=row["content_hash"],
                indexed_at=datetime.fromisoformat(row["indexed_at"]),
            )

    def add_document_and_chunks(
        self,
        document: DocumentMetadata,
        chunks: list[DocumentChunk],
    ) -> None:
        """Atomically insert or replace document metadata and all its chunks."""
        norm_path = str(Path(document.source_path).resolve())
        with self.transaction() as conn:
            # Delete existing document record if path exists (cascades to chunks)
            conn.execute("DELETE FROM indexed_documents WHERE source_path = ?;", (norm_path,))

            # Insert document
            conn.execute(
                """
                INSERT INTO indexed_documents (
                    id, source_path, file_name, file_type, file_size, modified_time, content_hash, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    document.document_id,
                    norm_path,
                    document.file_name,
                    document.file_type,
                    document.file_size,
                    document.modified_time,
                    document.content_hash,
                    document.indexed_at.isoformat(),
                ),
            )

            # Insert chunks
            for ch in chunks:
                emb = ch.embedding or [0.0] * self.embedding_dimensions
                blob = serialize_vector(emb)
                ch_path = str(Path(ch.source_path).resolve())
                conn.execute(
                    """
                    INSERT INTO document_chunks (
                        id, document_id, chunk_index, text, source_path, file_name, file_type, page_number, heading, embedding_blob
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ch.chunk_id,
                        document.document_id,
                        ch.chunk_index,
                        ch.text,
                        ch_path,
                        ch.file_name,
                        ch.file_type,
                        ch.page_number,
                        ch.heading,
                        blob,
                    ),
                )


    def remove_document(self, document_id: str) -> bool:
        """Remove a document and all its chunks by document_id."""
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM indexed_documents WHERE id = ?;", (document_id,))
            return cursor.rowcount > 0

    def remove_document_by_path(self, source_path: str) -> bool:
        """Remove a document and all its chunks by source_path."""
        norm_path = str(Path(source_path).resolve())
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM indexed_documents WHERE source_path = ?;", (norm_path,))
            return cursor.rowcount > 0

    def list_documents(self) -> list[DocumentMetadata]:
        """Return a list of all indexed documents."""
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM indexed_documents ORDER BY indexed_at DESC;").fetchall()
            return [
                DocumentMetadata(
                    document_id=r["id"],
                    source_path=r["source_path"],
                    file_name=r["file_name"],
                    file_type=r["file_type"],
                    file_size=r["file_size"],
                    modified_time=r["modified_time"],
                    content_hash=r["content_hash"],
                    indexed_at=datetime.fromisoformat(r["indexed_at"]),
                )
                for r in rows
            ]

    def get_document_count(self) -> int:
        """Return the total number of indexed documents."""
        with self.transaction() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM indexed_documents;").fetchone()
            return row["cnt"] if row else 0

    def get_chunk_count(self) -> int:
        """Return the total number of stored chunks across all documents."""
        with self.transaction() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM document_chunks;").fetchone()
            return row["cnt"] if row else 0

    def get_all_chunks(
        self,
        filter_path: Optional[str] = None,
        filter_type: Optional[str] = None,
    ) -> list[DocumentChunk]:
        """Fetch all chunks with deserialized embeddings, optionally filtered by path or type."""
        query = "SELECT * FROM document_chunks WHERE 1=1"
        params: list[str] = []

        if filter_path:
            norm_filter = str(Path(filter_path).resolve())
            query += " AND source_path LIKE ?"
            params.append(f"{norm_filter}%")

        if filter_type:
            query += " AND file_type = ?"
            params.append(filter_type.lower().lstrip("."))

        query += " ORDER BY source_path, chunk_index;"

        with self.transaction() as conn:
            rows = conn.execute(query, params).fetchall()
            chunks: list[DocumentChunk] = []
            for r in rows:
                emb = deserialize_vector(r["embedding_blob"])
                chunks.append(
                    DocumentChunk(
                        chunk_id=r["id"],
                        document_id=r["document_id"],
                        text=r["text"],
                        source_path=r["source_path"],
                        file_name=r["file_name"],
                        file_type=r["file_type"],
                        page_number=r["page_number"],
                        chunk_index=r["chunk_index"],
                        heading=r["heading"],
                        embedding=emb,
                    )
                )
            return chunks

    def cleanup_stale_documents(self) -> list[str]:
        """Detect and remove documents whose underlying files no longer exist on disk."""
        docs = self.list_documents()
        removed_paths: list[str] = []

        for d in docs:
            if not Path(d.source_path).exists():
                self.remove_document(d.document_id)
                removed_paths.append(d.source_path)
                self.logger.info("Cleaned up stale indexed document: %s", d.source_path)

        return removed_paths
