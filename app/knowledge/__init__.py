"""Personal Knowledge / Retrieval-Augmented Generation (RAG) subsystem."""

from app.knowledge.chunker import DocumentChunker
from app.knowledge.context import RAGContextBuilder
from app.knowledge.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    LocalHashEmbeddingProvider,
    OllamaEmbeddingProvider,
    get_embedding_provider,
)
from app.knowledge.index import KnowledgeDatabase, KnowledgeIndexError
from app.knowledge.manager import KnowledgeManager
from app.knowledge.models import (
    DocumentChunk,
    DocumentMetadata,
    IndexingResult,
    ParsedDocument,
    ParsedSection,
    ScoredChunk,
)
from app.knowledge.parsers import (
    BaseDocumentParser,
    ParserRegistry,
    PdfDocumentParser,
    TextDocumentParser,
    UnsupportedDocumentError,
)
from app.knowledge.retriever import Retriever

__all__ = [
    "BaseDocumentParser",
    "DocumentChunk",
    "DocumentChunker",
    "DocumentMetadata",
    "EmbeddingError",
    "EmbeddingProvider",
    "IndexingResult",
    "KnowledgeDatabase",
    "KnowledgeIndexError",
    "KnowledgeManager",
    "LocalHashEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "ParsedDocument",
    "ParsedSection",
    "ParserRegistry",
    "PdfDocumentParser",
    "RAGContextBuilder",
    "Retriever",
    "ScoredChunk",
    "TextDocumentParser",
    "UnsupportedDocumentError",
    "get_embedding_provider",
]
