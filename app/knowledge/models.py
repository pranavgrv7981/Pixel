"""Data models for Phase 9 Personal Knowledge / RAG pipeline."""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata representing an indexed document."""

    document_id: str = Field(description="Unique identifier (UUID) for the document")
    source_path: str = Field(description="Resolved path of the source file on disk")
    file_name: str = Field(description="Basename of the file")
    file_type: str = Field(description="File extension without leading dot (e.g. 'txt', 'pdf', 'py')")
    file_size: int = Field(description="File size in bytes")
    modified_time: float = Field(description="POSIX timestamp of last file modification")
    content_hash: str = Field(description="SHA-256 hash of the file content")
    indexed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when document was indexed",
    )


class ParsedSection(BaseModel):
    """A logical section extracted from a parsed document."""

    text: str = Field(description="Extracted raw text content of the section")
    page_number: Optional[int] = Field(default=None, description="1-indexed page number if applicable (e.g. for PDFs)")
    heading: Optional[str] = Field(default=None, description="Heading or structural label if present")


class ParsedDocument(BaseModel):
    """Intermediate structured output from document parsing."""

    metadata: DocumentMetadata
    sections: list[ParsedSection] = Field(default_factory=list)
    is_extractable: bool = Field(default=True, description="False if document contains no extractable text (e.g. image-only PDF)")
    warning: Optional[str] = Field(default=None, description="Warning message encountered during parsing")


class DocumentChunk(BaseModel):
    """A discrete, indexed chunk of a document suitable for retrieval."""

    chunk_id: str = Field(description="Unique UUID for this chunk")
    document_id: str = Field(description="Foreign key pointing to the parent document")
    text: str = Field(description="Chunk text content")
    source_path: str = Field(description="Path to the originating file")
    file_name: str = Field(description="Basename of originating file")
    file_type: str = Field(description="File extension")
    page_number: Optional[int] = Field(default=None, description="Page number where chunk appears (1-indexed)")
    chunk_index: int = Field(description="0-indexed position within parent document")
    heading: Optional[str] = Field(default=None, description="Contextual heading of the chunk")
    embedding: Optional[list[float]] = Field(default=None, description="Embedding vector representation")


class ScoredChunk(BaseModel):
    """A retrieved chunk paired with relevance scores."""

    chunk: DocumentChunk
    score: float = Field(description="Combined relevance score between 0.0 and 1.0")
    vector_score: float = Field(default=0.0, description="Cosine similarity score")
    lexical_score: float = Field(default=0.0, description="BM25/keyword lexical score")


class IndexingResult(BaseModel):
    """Structured report returned after an indexing operation."""

    documents_processed: int = 0
    documents_indexed: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    chunks_created: int = 0
    errors: list[dict[str, str]] = Field(default_factory=list)
    elapsed_time_seconds: float = 0.0
