"""Tests for structure-aware document chunker."""

from pathlib import Path
import pytest

from app.knowledge.chunker import DocumentChunker
from app.knowledge.models import DocumentMetadata, ParsedDocument, ParsedSection


def test_chunking_short_document() -> None:
    meta = DocumentMetadata(
        document_id="doc-1",
        source_path="/data/test.txt",
        file_name="test.txt",
        file_type="txt",
        file_size=50,
        modified_time=1000.0,
        content_hash="abc123",
    )
    doc = ParsedDocument(
        metadata=meta,
        sections=[ParsedSection(text="A short paragraph within chunk limit.")],
    )

    chunker = DocumentChunker(chunk_size=1000, chunk_overlap=150)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 1
    assert chunks[0].document_id == "doc-1"
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "A short paragraph within chunk limit."


def test_chunking_oversized_document_with_overlap() -> None:
    meta = DocumentMetadata(
        document_id="doc-2",
        source_path="/data/long.txt",
        file_name="long.txt",
        file_type="txt",
        file_size=5000,
        modified_time=1000.0,
        content_hash="hash2",
    )
    long_para = "Sentence number one about topic. " * 30  # ~960 chars
    doc = ParsedDocument(
        metadata=meta,
        sections=[
            ParsedSection(text=long_para),
            ParsedSection(text="Second section with more content. " * 20),
        ],
    )

    chunker = DocumentChunker(chunk_size=300, chunk_overlap=50)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) > 3
    # Sequential indexing
    for idx, ch in enumerate(chunks):
        assert ch.chunk_index == idx
        assert len(ch.text) > 0


def test_chunking_preserves_pdf_page_numbers() -> None:
    meta = DocumentMetadata(
        document_id="pdf-1",
        source_path="/data/doc.pdf",
        file_name="doc.pdf",
        file_type="pdf",
        file_size=1000,
        modified_time=1000.0,
        content_hash="pdfhash",
    )
    doc = ParsedDocument(
        metadata=meta,
        sections=[
            ParsedSection(text="Page one content about compilers.", page_number=1),
            ParsedSection(text="Page two content about parsers.", page_number=2),
        ],
    )

    chunker = DocumentChunker(chunk_size=500, chunk_overlap=50)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 2


def test_code_aware_chunking() -> None:
    meta = DocumentMetadata(
        document_id="code-1",
        source_path="/data/mod.py",
        file_name="mod.py",
        file_type="py",
        file_size=2000,
        modified_time=1000.0,
        content_hash="codehash",
    )
    code = """
def func_one():
    x = 1
    return x

def func_two():
    y = 2
    return y

class MyService:
    def process(self):
        pass
"""
    doc = ParsedDocument(
        metadata=meta,
        sections=[ParsedSection(text=code.strip())],
    )

    chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 2
    # Ensure no empty chunks
    assert all(len(c.text.strip()) > 0 for c in chunks)
