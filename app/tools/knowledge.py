"""Knowledge and RAG tools integrated with ToolRegistry, PathGuard, and PermissionManager."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.tools.base import RiskLevel, Tool, ToolResult

if TYPE_CHECKING:
    from app.knowledge.manager import KnowledgeManager


# --- Input Schemas ---

class SearchKnowledgeArgs(BaseModel):
    """Input arguments for searching the local knowledge index."""

    query: str = Field(
        description="The question, keywords, or concepts to search for within indexed documents",
    )
    top_k: Optional[int] = Field(
        default=4,
        ge=1,
        le=20,
        description="Maximum number of relevant chunks to retrieve (default 4, max 20)",
    )
    filter_doc: Optional[str] = Field(
        default=None,
        description="Optional filter to match a specific document filename or path",
    )
    filter_type: Optional[str] = Field(
        default=None,
        description="Optional filter by file type (e.g. 'pdf', 'py', 'txt', 'md')",
    )


class ListIndexedDocumentsArgs(BaseModel):
    """Input arguments for listing indexed documents."""


class IndexDocumentArgs(BaseModel):
    """Input arguments for indexing a single local document."""

    path: str = Field(
        description="Relative or absolute path to the local document to index (must be within allowed roots)",
    )


class IndexDirectoryArgs(BaseModel):
    """Input arguments for indexing a directory of local documents."""

    path: str = Field(
        description="Relative or absolute path to the directory to index (must be within allowed roots)",
    )
    recursive: Optional[bool] = Field(
        default=True,
        description="Whether to index subdirectories recursively (default True)",
    )


class RemoveDocumentArgs(BaseModel):
    """Input arguments for removing a document from the knowledge index."""

    path: str = Field(
        description="Path of the indexed document to remove from the knowledge index",
    )


# --- Base Knowledge Tool ---

class BaseKnowledgeTool(Tool):
    """Base class for personal knowledge and RAG tools."""

    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        args_model: Optional[type[BaseModel]] = None,
        knowledge_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(name=name, description=description, risk_level=risk_level, args_model=args_model)
        self.settings = settings or get_settings()
        if knowledge_manager is None:
            from app.knowledge.manager import KnowledgeManager

            self.knowledge_manager = KnowledgeManager(settings=self.settings)
        else:
            self.knowledge_manager = knowledge_manager



# --- Tool Implementations ---

class SearchKnowledgeTool(BaseKnowledgeTool):
    """Tool to search indexed local documents and retrieve grounded context with citations."""

    def __init__(
        self,
        knowledge_manager: Optional[KnowledgeManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="search_knowledge",
            description="Search local indexed documents (PDFs, notes, source code, manuals) for relevant context to answer questions.",
            risk_level=RiskLevel.READ,
            args_model=SearchKnowledgeArgs,
            knowledge_manager=knowledge_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        query = args["query"]
        top_k = args.get("top_k") or 4
        filter_doc = args.get("filter_doc")
        filter_type = args.get("filter_type")

        scored_chunks, context_text = self.knowledge_manager.search(
            query=query,
            top_k=top_k,
            filter_doc=filter_doc,
            filter_type=filter_type,
        )

        if not scored_chunks:
            return ToolResult(
                success=True,
                data={
                    "count": 0,
                    "sources": [],
                    "context_text": "",
                    "message": f"No sufficiently relevant knowledge found in indexed documents for query: '{query}'.",
                },
                message=f"No matching documents or passages found for '{query}'.",
            )

        sources_summary = self.knowledge_manager.context_builder.build_sources_metadata(scored_chunks)
        return ToolResult(
            success=True,
            data={
                "count": len(scored_chunks),
                "sources": sources_summary,
                "context_text": context_text,
                "message": f"Retrieved {len(scored_chunks)} relevant passages from indexed documents.",
            },
            message=f"Retrieved {len(scored_chunks)} relevant passages for '{query}'.",
        )


class ListIndexedDocumentsTool(BaseKnowledgeTool):
    """Tool to view all currently indexed documents in the local knowledge base."""

    def __init__(
        self,
        knowledge_manager: Optional[KnowledgeManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="list_indexed_documents",
            description="List all local documents currently indexed in the personal knowledge base.",
            risk_level=RiskLevel.READ,
            args_model=ListIndexedDocumentsArgs,
            knowledge_manager=knowledge_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        docs = self.knowledge_manager.list_documents()
        items = [
            {
                "document_id": d.document_id,
                "file_name": d.file_name,
                "source_path": d.source_path,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "indexed_at": d.indexed_at.isoformat(),
            }
            for d in docs
        ]
        return ToolResult(
            success=True,
            data={
                "count": len(items),
                "documents": items,
            },
            message=f"Total indexed documents: {len(items)}",
        )


class IndexDocumentTool(BaseKnowledgeTool):
    """Tool to parse, chunk, embed, and index a single local document file."""

    def __init__(
        self,
        knowledge_manager: Optional[KnowledgeManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="index_document",
            description="Index a single local document (PDF, TXT, MD, code file) into the personal knowledge base. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=IndexDocumentArgs,
            knowledge_manager=knowledge_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = args["path"]
        result = self.knowledge_manager.index_file(path)

        success = result.documents_indexed > 0 or (result.documents_skipped > 0 and not result.errors)
        if result.documents_indexed > 0:
            msg = f"Successfully indexed '{path}' ({result.chunks_created} chunks created)."
        elif result.documents_skipped > 0 and not result.errors:
            msg = f"Document '{path}' is already up-to-date in the index (skipped)."
        else:
            err_details = "; ".join(e["error"] for e in result.errors) if result.errors else "Unknown indexing failure"
            msg = f"Failed to index '{path}': {err_details}"

        return ToolResult(
            success=success,
            data=result.model_dump(),
            message=msg,
            error=None if success else msg,
        )


class IndexDirectoryTool(BaseKnowledgeTool):
    """Tool to index all supported documents in a local directory."""

    def __init__(
        self,
        knowledge_manager: Optional[KnowledgeManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="index_directory",
            description="Index all supported documents within a local directory into the personal knowledge base. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=IndexDirectoryArgs,
            knowledge_manager=knowledge_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = args["path"]
        recursive = args.get("recursive", True)
        result = self.knowledge_manager.index_directory(path, recursive=recursive)

        msg = (
            f"Directory indexing complete for '{path}': "
            f"{result.documents_indexed} indexed, {result.documents_skipped} skipped, "
            f"{result.documents_failed} failed across {result.documents_processed} files."
        )

        return ToolResult(
            success=result.documents_failed == 0 or result.documents_indexed > 0,
            data=result.model_dump(),
            message=msg,
            error=None if result.documents_failed == 0 else f"Encountered {result.documents_failed} file errors",
        )


class RemoveDocumentTool(BaseKnowledgeTool):
    """Tool to remove a document and all its chunks from the knowledge index."""

    def __init__(
        self,
        knowledge_manager: Optional[KnowledgeManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        super().__init__(
            name="remove_document",
            description="Remove a document from the personal knowledge index. Requires confirmation.",
            risk_level=RiskLevel.MEDIUM,
            args_model=RemoveDocumentArgs,
            knowledge_manager=knowledge_manager,
            settings=settings,
        )

    def _run(self, args: dict[str, Any]) -> ToolResult:
        path = args["path"]
        removed = self.knowledge_manager.remove_file(path)

        if removed:
            msg = f"Document '{path}' and all associated chunks were successfully removed."
        else:
            msg = f"Document '{path}' was not found in the knowledge index or could not be removed."

        return ToolResult(
            success=removed,
            data={"path": path, "removed": removed},
            message=msg,
            error=None if removed else f"Document '{path}' not found in index",
        )
