"""Tests for hybrid vector and lexical retrieval ranking and filtering."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.core.config import Settings
from app.knowledge.embeddings import LocalHashEmbeddingProvider
from app.knowledge.index import KnowledgeDatabase
from app.knowledge.models import DocumentChunk, DocumentMetadata
from app.knowledge.retriever import Retriever


@pytest.fixture
def populated_retriever(tmp_path: Path) -> Retriever:
    db_file = tmp_path / "test_retriever.db"
    settings = Settings(
        knowledge_database_path=str(db_file),
        rag_top_k=2,
        rag_min_score=0.15,
    )
    provider = LocalHashEmbeddingProvider(dimensions=384)
    db = KnowledgeDatabase(db_path=db_file, settings=settings, embedding_dimensions=384)
    db.initialize()

    # Create 3 distinct documents: AFL notes, Probability, Operating Systems
    doc_afl = DocumentMetadata(
        document_id="doc-afl",
        source_path="/data/afl_notes.txt",
        file_name="afl_notes.txt",
        file_type="txt",
        file_size=200,
        modified_time=1.0,
        content_hash="hafl",
        indexed_at=datetime.now(timezone.utc),
    )
    chunk_afl = DocumentChunk(
        chunk_id="ch-afl",
        document_id="doc-afl",
        text="A lambda closure captures variables from its lexical environment scope in AFL notes.",
        source_path="/data/afl_notes.txt",
        file_name="afl_notes.txt",
        file_type="txt",
        chunk_index=0,
        embedding=provider.embed_text("A lambda closure captures variables from its lexical environment scope in AFL notes."),
    )

    doc_prob = DocumentMetadata(
        document_id="doc-prob",
        source_path="/data/probability.txt",
        file_name="probability.txt",
        file_type="txt",
        file_size=200,
        modified_time=1.0,
        content_hash="hprob",
        indexed_at=datetime.now(timezone.utc),
    )
    chunk_prob = DocumentChunk(
        chunk_id="ch-prob",
        document_id="doc-prob",
        text="Bayes theorem calculates posterior probability using prior probability and likelihood.",
        source_path="/data/probability.txt",
        file_name="probability.txt",
        file_type="txt",
        chunk_index=0,
        embedding=provider.embed_text("Bayes theorem calculates posterior probability using prior probability and likelihood."),
    )

    doc_os = DocumentMetadata(
        document_id="doc-os",
        source_path="/data/os.txt",
        file_name="os.txt",
        file_type="txt",
        file_size=200,
        modified_time=1.0,
        content_hash="hos",
        indexed_at=datetime.now(timezone.utc),
    )
    chunk_os = DocumentChunk(
        chunk_id="ch-os",
        document_id="doc-os",
        text="Virtual memory uses page tables and TLB to translate logical addresses to physical memory frames.",
        source_path="/data/os.txt",
        file_name="os.txt",
        file_type="txt",
        chunk_index=0,
        embedding=provider.embed_text("Virtual memory uses page tables and TLB to translate logical addresses to physical memory frames."),
    )

    db.add_document_and_chunks(doc_afl, [chunk_afl])
    db.add_document_and_chunks(doc_prob, [chunk_prob])
    db.add_document_and_chunks(doc_os, [chunk_os])

    return Retriever(db=db, embedding_provider=provider, settings=settings)


def test_retrieval_ranks_correct_document_highest(populated_retriever: Retriever) -> None:
    results = populated_retriever.search("What is a lambda closure in AFL?")
    assert len(results) >= 1
    top = results[0]
    assert top.chunk.file_name == "afl_notes.txt"
    assert "lambda closure" in top.chunk.text
    assert top.score > 0.3


def test_retrieval_probability_query(populated_retriever: Retriever) -> None:
    results = populated_retriever.search("How does Bayes theorem work?")
    assert len(results) >= 1
    top = results[0]
    assert top.chunk.file_name == "probability.txt"
    assert "Bayes theorem" in top.chunk.text


def test_retrieval_metadata_filter(populated_retriever: Retriever) -> None:
    # Filter strictly to probability document
    results = populated_retriever.search("memory or probability", filter_doc="probability.txt")
    assert len(results) == 1
    assert results[0].chunk.file_name == "probability.txt"


def test_no_hit_on_completely_unrelated_query(populated_retriever: Retriever) -> None:
    # Query with very high min_score threshold to test no-hit behavior
    results = populated_retriever.search("Ancient Roman architecture and Colosseum construction", min_score=0.85)
    assert results == []
