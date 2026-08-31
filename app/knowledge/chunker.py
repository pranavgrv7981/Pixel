"""Deterministic, structure-aware document chunking implementation."""

import re
from typing import Optional
import uuid

from app.core.config import Settings, get_settings
from app.knowledge.models import DocumentChunk, ParsedDocument, ParsedSection


class DocumentChunker:
    """Chunks parsed documents into bounded, indexed text segments with metadata."""

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        cfg = settings or get_settings()
        self.chunk_size = chunk_size or cfg.chunk_size
        self.chunk_overlap = chunk_overlap or cfg.chunk_overlap
        if self.chunk_overlap >= self.chunk_size:
            self.chunk_overlap = self.chunk_size // 5

    def chunk_document(self, document: ParsedDocument) -> list[DocumentChunk]:
        """Convert all sections of a parsed document into a list of DocumentChunks."""
        if not document.is_extractable or not document.sections:
            return []

        chunks: list[DocumentChunk] = []
        global_chunk_idx = 0

        for section in document.sections:
            section_chunks = self._chunk_section(
                section=section,
                document=document,
                start_index=global_chunk_idx,
            )
            for ch in section_chunks:
                chunks.append(ch)
                global_chunk_idx += 1

        return chunks

    def _chunk_section(
        self,
        section: ParsedSection,
        document: ParsedDocument,
        start_index: int,
    ) -> list[DocumentChunk]:
        text = section.text.strip()
        if not text:
            return []

        # If section is already within chunk size limit, emit as single chunk
        if len(text) <= self.chunk_size:
            return [
                DocumentChunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document.metadata.document_id,
                    text=text,
                    source_path=document.metadata.source_path,
                    file_name=document.metadata.file_name,
                    file_type=document.metadata.file_type,
                    page_number=section.page_number,
                    chunk_index=start_index,
                    heading=section.heading,
                )
            ]

        # Break into structured pieces (paragraphs or logical blocks)
        is_code = document.metadata.file_type in {"py", "c", "h", "cpp", "hpp", "java", "js", "ts", "html", "css"}
        if is_code:
            split_units = self._split_code_units(text)
        else:
            split_units = self._split_text_units(text)

        raw_chunks: list[str] = []
        current_unit: list[str] = []
        current_len = 0

        for unit in split_units:
            unit_len = len(unit)
            if current_len + unit_len > self.chunk_size and current_unit:
                # Flush current block
                raw_chunks.append("\n\n".join(current_unit).strip())

                # Retain overlap from end of current unit
                overlap_text: list[str] = []
                overlap_len = 0
                for prev in reversed(current_unit):
                    if overlap_len + len(prev) <= self.chunk_overlap:
                        overlap_text.insert(0, prev)
                        overlap_len += len(prev)
                    else:
                        break

                current_unit = overlap_text
                current_len = overlap_len

            current_unit.append(unit)
            current_len += unit_len

        if current_unit:
            final_text = "\n\n".join(current_unit).strip()
            if final_text and (not raw_chunks or final_text != raw_chunks[-1]):
                raw_chunks.append(final_text)

        # Build DocumentChunk instances
        result: list[DocumentChunk] = []
        for idx, chunk_text in enumerate(raw_chunks):
            if chunk_text.strip():
                result.append(
                    DocumentChunk(
                        chunk_id=str(uuid.uuid4()),
                        document_id=document.metadata.document_id,
                        text=chunk_text.strip(),
                        source_path=document.metadata.source_path,
                        file_name=document.metadata.file_name,
                        file_type=document.metadata.file_type,
                        page_number=section.page_number,
                        chunk_index=start_index + idx,
                        heading=section.heading,
                    )
                )

        return result

    def _split_text_units(self, text: str) -> list[str]:
        """Split prose/markdown by double newlines, falling back to sentences if a block is oversized."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        units: list[str] = []

        for para in paragraphs:
            if len(para) <= self.chunk_size:
                units.append(para)
            else:
                # Split oversized paragraph by sentence delimiters
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
                for s in sentences:
                    if len(s) <= self.chunk_size:
                        units.append(s)
                    else:
                        # Hard split by word sliding window if sentence is huge
                        words = s.split()
                        sub: list[str] = []
                        sub_len = 0
                        for w in words:
                            if sub_len + len(w) + 1 > self.chunk_size and sub:
                                units.append(" ".join(sub))
                                sub = [w]
                                sub_len = len(w)
                            else:
                                sub.append(w)
                                sub_len += len(w) + 1
                        if sub:
                            units.append(" ".join(sub))

        return units

    def _split_code_units(self, text: str) -> list[str]:
        """Split source code along function/class declarations or blank lines."""
        # Detect function / class definition boundaries
        lines = text.splitlines()
        units: list[str] = []
        current_block: list[str] = []

        boundary_pattern = re.compile(r"^(?:def |class |async def |void |int |char |float |double |public |private |protected |function )")

        for line in lines:
            if boundary_pattern.match(line.strip()) and current_block:
                block_str = "\n".join(current_block).strip()
                if block_str:
                    units.append(block_str)
                current_block = [line]
            else:
                current_block.append(line)

        if current_block:
            block_str = "\n".join(current_block).strip()
            if block_str:
                units.append(block_str)

        return units if units else [text]
