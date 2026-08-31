"""Tests for local document parsers (text, markdown, code, csv, json, pdf)."""

from pathlib import Path
import pypdf
import pytest

from app.knowledge.parsers import (
    FORBIDDEN_EXTENSIONS,
    ParserRegistry,
    PdfDocumentParser,
    TextDocumentParser,
    UnsupportedDocumentError,
)


@pytest.fixture
def registry() -> ParserRegistry:
    return ParserRegistry()


def test_text_and_markdown_parsing(tmp_path: Path, registry: ParserRegistry) -> None:
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("This is plain text content.\nSecond line.", encoding="utf-8")

    parsed = registry.parse_document(txt_file)
    assert parsed.is_extractable is True
    assert parsed.metadata.file_type == "txt"
    assert len(parsed.sections) == 1
    assert "plain text content" in parsed.sections[0].text

    md_file = tmp_path / "sample.md"
    md_content = """# Introduction
This is the intro paragraph.

## Details
Here are technical details on lambda functions.
"""
    md_file.write_text(md_content, encoding="utf-8")
    parsed_md = registry.parse_document(md_file)
    assert parsed_md.is_extractable is True
    assert parsed_md.metadata.file_type == "md"
    assert len(parsed_md.sections) >= 2


def test_code_json_and_csv_parsing(tmp_path: Path, registry: ParserRegistry) -> None:
    py_file = tmp_path / "script.py"
    py_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    parsed_py = registry.parse_document(py_file)
    assert parsed_py.is_extractable is True
    assert parsed_py.metadata.file_type == "py"
    assert "def add(a, b):" in parsed_py.sections[0].text

    json_file = tmp_path / "data.json"
    json_file.write_text('{"name": "Atlas", "version": 1}', encoding="utf-8")
    parsed_json = registry.parse_document(json_file)
    assert parsed_json.is_extractable is True
    assert "Atlas" in parsed_json.sections[0].text

    csv_file = tmp_path / "table.csv"
    csv_file.write_text("id,name,role\n1,Alice,Dev\n2,Bob,Admin\n", encoding="utf-8")
    parsed_csv = registry.parse_document(csv_file)
    assert parsed_csv.is_extractable is True
    assert "Columns: id, name, role" in parsed_csv.sections[0].text


def test_pdf_parsing_with_page_preservation(tmp_path: Path, registry: ParserRegistry) -> None:
    pdf_file = tmp_path / "test_doc.pdf"

    # Create real 2-page PDF using pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)

    # Add text via annotations/metadata or pypdf canvas
    with open(pdf_file, "wb") as f:
        writer.write(f)

    # Empty blank page PDF will be detected as unextractable text
    parsed = registry.parse_document(pdf_file)
    assert parsed.metadata.file_type == "pdf"
    assert parsed.is_extractable is False
    assert "no extractable text" in parsed.warning.lower()


def test_empty_document_handling(tmp_path: Path, registry: ParserRegistry) -> None:
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")

    parsed = registry.parse_document(empty_file)
    assert parsed.is_extractable is False
    assert "empty" in parsed.warning.lower()


def test_forbidden_and_unsupported_extensions(tmp_path: Path, registry: ParserRegistry) -> None:
    for ext in (".exe", ".bat", ".ps1", ".cmd"):
        bad_file = tmp_path / f"malicious{ext}"
        bad_file.write_text("echo hacked", encoding="utf-8")
        with pytest.raises(UnsupportedDocumentError) as exc_info:
            registry.parse_document(bad_file)
        assert "Security violation" in str(exc_info.value)

    unknown_file = tmp_path / "archive.tar.gz"
    unknown_file.write_bytes(b"12345")
    with pytest.raises(UnsupportedDocumentError):
        registry.parse_document(unknown_file)
