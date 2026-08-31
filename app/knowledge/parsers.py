"""Document parsers for extracting text and structure from local files."""

from abc import ABC, abstractmethod
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Optional
import uuid

from app.core.exceptions import ToolExecutionError
from app.knowledge.models import DocumentMetadata, ParsedDocument, ParsedSection

# Strictly forbidden file extensions that must never be parsed or executed
FORBIDDEN_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".dll", ".sys", ".com",
    ".scr", ".jar", ".bin", ".iso", ".vhd", ".pyc", ".pyd",
}

TEXT_AND_CODE_EXTENSIONS = {
    ".txt", ".md", ".py", ".c", ".h", ".cpp", ".hpp", ".java", ".js",
    ".ts", ".html", ".htm", ".css", ".json", ".csv", ".yaml", ".yml",
    ".toml", ".ini", ".conf", ".sh", ".sql", ".rst",
}


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file efficiently using chunked reads."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class UnsupportedDocumentError(ToolExecutionError):
    """Raised when an unsupported or forbidden file format is submitted for parsing."""


class BaseDocumentParser(ABC):
    """Abstract interface for file-type specific document parsers."""

    @abstractmethod
    def can_parse(self, extension: str) -> bool:
        """Check if parser handles this file extension (including dot)."""

    @abstractmethod
    def parse(self, path: Path) -> ParsedDocument:
        """Parse file content and extract sections with metadata."""


class TextDocumentParser(BaseDocumentParser):
    """Parser for plaintext, markdown, CSV, JSON, and source code files."""

    def can_parse(self, extension: str) -> bool:
        return extension.lower() in TEXT_AND_CODE_EXTENSIONS

    def parse(self, path: Path) -> ParsedDocument:
        stat = path.stat()
        file_hash = compute_file_hash(path)
        ext = path.suffix.lower().lstrip(".")

        metadata = DocumentMetadata(
            document_id=str(uuid.uuid4()),
            source_path=str(path.resolve()),
            file_name=path.name,
            file_type=ext,
            file_size=stat.st_size,
            modified_time=stat.st_mtime,
            content_hash=file_hash,
        )

        # Attempt UTF-8 with fallback to latin-1 to avoid decoding exceptions
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        if not content.strip():
            return ParsedDocument(
                metadata=metadata,
                sections=[],
                is_extractable=False,
                warning="Document is empty.",
            )

        sections: list[ParsedSection] = []

        # Specialized handling by extension
        if ext == "md":
            # Split sections by top-level or second-level headings
            lines = content.splitlines()
            current_heading: Optional[str] = None
            current_chunk_lines: list[str] = []

            for line in lines:
                if line.startswith("#"):
                    if current_chunk_lines:
                        text_block = "\n".join(current_chunk_lines).strip()
                        if text_block:
                            sections.append(ParsedSection(text=text_block, heading=current_heading))
                        current_chunk_lines = []
                    current_heading = line.strip()
                current_chunk_lines.append(line)

            if current_chunk_lines:
                text_block = "\n".join(current_chunk_lines).strip()
                if text_block:
                    sections.append(ParsedSection(text=text_block, heading=current_heading))

        elif ext == "csv":
            try:
                reader = csv.reader(io.StringIO(content))
                rows = list(reader)
                if rows:
                    header = rows[0]
                    formatted_rows = [f"Columns: {', '.join(header)}"]
                    for idx, row in enumerate(rows[1:], start=1):
                        formatted_rows.append(f"Row {idx}: {', '.join(row)}")
                    sections.append(ParsedSection(text="\n".join(formatted_rows), heading="CSV Content"))
                else:
                    sections.append(ParsedSection(text=content, heading=None))
            except Exception:
                sections.append(ParsedSection(text=content, heading=None))

        elif ext == "json":
            try:
                data = json.loads(content)
                pretty = json.dumps(data, indent=2)
                sections.append(ParsedSection(text=pretty, heading="JSON Data"))
            except Exception:
                sections.append(ParsedSection(text=content, heading=None))

        else:
            # Source code or generic plain text
            sections.append(ParsedSection(text=content, heading=None))

        return ParsedDocument(
            metadata=metadata,
            sections=sections,
            is_extractable=True,
        )


class PdfDocumentParser(BaseDocumentParser):
    """Parser for Adobe Portable Document Format (PDF) files preserving page numbers."""

    def can_parse(self, extension: str) -> bool:
        return extension.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDocument:
        import pypdf

        stat = path.stat()
        file_hash = compute_file_hash(path)

        metadata = DocumentMetadata(
            document_id=str(uuid.uuid4()),
            source_path=str(path.resolve()),
            file_name=path.name,
            file_type="pdf",
            file_size=stat.st_size,
            modified_time=stat.st_mtime,
            content_hash=file_hash,
        )

        try:
            reader = pypdf.PdfReader(str(path))
        except Exception as err:
            return ParsedDocument(
                metadata=metadata,
                sections=[],
                is_extractable=False,
                warning=f"PDF parsing error: {err}",
            )

        sections: list[ParsedSection] = []
        total_extracted_chars = 0

        for page_idx, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                cleaned = page_text.strip()
                if cleaned:
                    total_extracted_chars += len(cleaned)
                    sections.append(
                        ParsedSection(
                            text=cleaned,
                            page_number=page_idx,
                            heading=f"Page {page_idx}",
                        )
                    )
            except Exception:
                continue

        if total_extracted_chars == 0:
            return ParsedDocument(
                metadata=metadata,
                sections=[],
                is_extractable=False,
                warning="PDF contains no extractable text (likely scanned or image-only).",
            )

        return ParsedDocument(
            metadata=metadata,
            sections=sections,
            is_extractable=True,
        )


class ParserRegistry:
    """Central registry of document parsers with extension dispatching and security checks."""

    def __init__(self) -> None:
        self._parsers: list[BaseDocumentParser] = [
            TextDocumentParser(),
            PdfDocumentParser(),
        ]

    def register_parser(self, parser: BaseDocumentParser) -> None:
        """Register an additional parser."""
        self._parsers.insert(0, parser)

    def is_supported(self, path: Path) -> bool:
        """Check if file has an approved and supported parser."""
        ext = path.suffix.lower()
        if ext in FORBIDDEN_EXTENSIONS:
            return False
        return any(p.can_parse(ext) for p in self._parsers)

    def parse_document(self, path: Path) -> ParsedDocument:
        """Locate appropriate parser and parse document, raising UnsupportedDocumentError if unknown."""
        ext = path.suffix.lower()

        if ext in FORBIDDEN_EXTENSIONS:
            raise UnsupportedDocumentError(f"Security violation: Executable/script file type '{ext}' cannot be parsed")

        for parser in self._parsers:
            if parser.can_parse(ext):
                return parser.parse(path)

        raise UnsupportedDocumentError(f"Unsupported document type: '{ext}'. Supported types include .txt, .md, code, and .pdf")
