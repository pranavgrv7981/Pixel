"""High-level KnowledgeManager coordinating indexing, parsing, chunking, and retrieval."""

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolExecutionError, ToolValidationError
from app.core.logging import get_logger
from app.knowledge.chunker import DocumentChunker
from app.knowledge.context import RAGContextBuilder
from app.knowledge.embeddings import EmbeddingProvider, get_embedding_provider
from app.knowledge.index import KnowledgeDatabase
from app.knowledge.models import DocumentMetadata, IndexingResult, ScoredChunk
from app.knowledge.parsers import ParserRegistry
from app.tools.path_guard import PathGuard


class KnowledgeManager:
    """Central orchestrator for the local Personal Knowledge / RAG subsystem."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        path_guard: Optional[PathGuard] = None,
        db: Optional[KnowledgeDatabase] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        chunker: Optional[DocumentChunker] = None,
        context_builder: Optional[RAGContextBuilder] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.path_guard = path_guard or PathGuard(settings=self.settings)
        self.embedding_provider = embedding_provider or get_embedding_provider(self.settings)
        self.db = db or KnowledgeDatabase(
            settings=self.settings,
            embedding_model=self.embedding_provider.model_name,
            embedding_dimensions=self.embedding_provider.dimensions,
        )
        self.parsers = ParserRegistry()
        self.chunker = chunker or DocumentChunker(settings=self.settings)
        self.context_builder = context_builder or RAGContextBuilder(settings=self.settings)
        self.logger = get_logger("knowledge.manager")

        # Lazy import of Retriever to avoid circular dependencies
        from app.knowledge.retriever import Retriever

        self.retriever = Retriever(
            db=self.db,
            embedding_provider=self.embedding_provider,
            settings=self.settings,
        )

    def initialize(self) -> None:
        """Initialize SQLite database schema and knowledge directory."""
        self.settings.ensure_directories()
        self.db.initialize()

    def index_file(self, file_path: str | Path) -> IndexingResult:
        """Parse, chunk, embed, and index a single document file."""
        start_time = time.time()
        result = IndexingResult(documents_processed=1)

        # 1. Validate path against allowed roots
        try:
            resolved_path = self.path_guard.validate_path(file_path, check_exists=True, must_be_file=True)
        except Exception as err:
            result.documents_failed = 1
            result.errors.append({"file": str(file_path), "error": str(err)})
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result


        # 2. Check file size limit
        file_size = resolved_path.stat().st_size
        if file_size > self.settings.max_document_size_bytes:
            result.documents_skipped = 1
            result.errors.append({
                "file": str(resolved_path),
                "error": f"File size ({file_size} bytes) exceeds maximum limit ({self.settings.max_document_size_bytes} bytes)",
            })
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result

        # 3. Check parser support
        if not self.parsers.is_supported(resolved_path):
            result.documents_skipped = 1
            result.errors.append({
                "file": str(resolved_path),
                "error": f"Unsupported or forbidden file format: '{resolved_path.suffix}'",
            })
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result

        # 4. Incremental indexing check (skip if unchanged)
        existing = self.db.get_document_by_path(str(resolved_path))
        from app.knowledge.parsers import compute_file_hash

        current_hash = compute_file_hash(resolved_path)
        current_mtime = resolved_path.stat().st_mtime

        if existing is not None and existing.content_hash == current_hash and abs(existing.modified_time - current_mtime) < 1e-3:
            self.logger.info("Skipping unchanged document: %s", resolved_path)
            result.documents_skipped = 1
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result

        # 5. Parse document
        try:
            parsed = self.parsers.parse_document(resolved_path)
        except Exception as err:
            self.logger.error("Failed to parse document '%s': %s", resolved_path, err)
            result.documents_failed = 1
            result.errors.append({"file": str(resolved_path), "error": f"Parsing failed: {err}"})
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result

        if not parsed.is_extractable:
            self.logger.warning("Document '%s' not extractable: %s", resolved_path, parsed.warning)
            result.documents_skipped = 1
            result.errors.append({"file": str(resolved_path), "error": parsed.warning or "No extractable text"})
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result

        # 6. Chunk document
        chunks = self.chunker.chunk_document(parsed)
        if not chunks:
            result.documents_skipped = 1
            result.errors.append({"file": str(resolved_path), "error": "Document produced zero text chunks"})
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result

        # 7. Compute embeddings for chunks
        chunk_texts = [ch.text for ch in chunks]
        try:
            embeddings = self.embedding_provider.embed_documents(chunk_texts)
            for ch, emb in zip(chunks, embeddings):
                ch.embedding = emb
        except Exception as err:
            self.logger.error("Embedding generation failed for '%s': %s", resolved_path, err)
            result.documents_failed = 1
            result.errors.append({"file": str(resolved_path), "error": f"Embedding error: {err}"})
            result.elapsed_time_seconds = round(time.time() - start_time, 3)
            return result

        # 8. Persist to SQLite knowledge database
        try:
            self.db.add_document_and_chunks(parsed.metadata, chunks)
            result.documents_indexed = 1
            result.chunks_created = len(chunks)
            self.logger.info(
                "Indexed document '%s' with %d chunks (hash=%s)",
                resolved_path.name,
                len(chunks),
                current_hash[:8],
            )
        except Exception as err:
            self.logger.error("Database persistence failed for '%s': %s", resolved_path, err)
            result.documents_failed = 1
            result.errors.append({"file": str(resolved_path), "error": f"Database error: {err}"})

        result.elapsed_time_seconds = round(time.time() - start_time, 3)
        return result

    def index_directory(
        self,
        directory_path: str | Path,
        recursive: bool = True,
    ) -> IndexingResult:
        """Scan and index all supported documents in a directory within allowed boundaries."""
        start_time = time.time()
        combined = IndexingResult()

        try:
            resolved_dir = self.path_guard.validate_path(directory_path, check_exists=True, must_be_dir=True)
        except Exception as err:
            combined.documents_failed = 1
            combined.errors.append({"file": str(directory_path), "error": str(err)})
            combined.elapsed_time_seconds = round(time.time() - start_time, 3)
            return combined

        # Collect files respecting limits
        pattern = "**/*" if recursive else "*"
        candidate_files: list[Path] = []

        for p in resolved_dir.glob(pattern):
            if p.is_file():
                # Discard non-supported or forbidden files early
                if self.parsers.is_supported(p):
                    candidate_files.append(p)
                if len(candidate_files) >= self.settings.max_indexed_files_per_operation:
                    self.logger.warning(
                        "Reached maximum files limit per indexing operation (%d)",
                        self.settings.max_indexed_files_per_operation,
                    )
                    break

        combined.documents_processed = len(candidate_files)

        # Index each candidate file with error isolation
        for file_path in candidate_files:
            file_res = self.index_file(file_path)
            combined.documents_indexed += file_res.documents_indexed
            combined.documents_skipped += file_res.documents_skipped
            combined.documents_failed += file_res.documents_failed
            combined.chunks_created += file_res.chunks_created
            combined.errors.extend(file_res.errors)

        combined.elapsed_time_seconds = round(time.time() - start_time, 3)
        return combined

    def remove_file(self, file_path: str | Path) -> bool:
        """Remove a document and all its chunks from the knowledge index."""
        try:
            resolved_path = self.path_guard.validate_path(file_path)
            return self.db.remove_document_by_path(str(resolved_path))
        except Exception as err:
            self.logger.error("Failed to remove document '%s': %s", file_path, err)
            return False


    def list_documents(self) -> list[DocumentMetadata]:
        """Return list of all indexed documents."""
        return self.db.list_documents()

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        filter_path: Optional[str] = None,
        filter_type: Optional[str] = None,
        filter_doc: Optional[str] = None,
    ) -> tuple[list[ScoredChunk], str]:
        """Search indexed documents and return ranked chunks along with injection-defended context block."""
        scored = self.retriever.search(
            query=query,
            top_k=top_k,
            min_score=min_score,
            filter_path=filter_path,
            filter_type=filter_type,
            filter_doc=filter_doc,
        )
        context_str = self.context_builder.build_context(scored)
        return scored, context_str

    def cleanup_stale(self) -> list[str]:
        """Remove documents whose files no longer exist on disk."""
        return self.db.cleanup_stale_documents()
