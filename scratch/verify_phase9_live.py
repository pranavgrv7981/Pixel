"""Verification script testing real live Ollama qwen3:30b RAG retrieval and question answering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pypdf


from app.agent.agent import Agent
from app.agent.conversation import Conversation
from app.core.config import get_settings
from app.core.ollama_client import OllamaClient
from app.knowledge.manager import KnowledgeManager
from app.memory.manager import MemoryManager
from app.security.confirmations import ConfirmationManager, ConfirmationProvider
from app.security.manager import PermissionManager
from app.tools.base import RiskLevel
from app.tools.knowledge import (
    IndexDocumentTool,
    ListIndexedDocumentsTool,
    SearchKnowledgeTool,
)
from app.tools.registry import ToolRegistry


class AutoApproveProvider(ConfirmationProvider):
    def request_confirmation(self, context, decision) -> bool:
        return True


def create_test_pdf(pdf_path: Path) -> None:
    writer = pypdf.PdfWriter()
    page1 = writer.add_blank_page(width=300, height=300)
    # Write a simple PDF text page using pypdf writer annotations or simple page layout
    # Alternatively we can write text if pypdf allows, or create sample text file
    writer.add_metadata({"/Title": "Sample PDF Document"})
    with open(pdf_path, "wb") as f:
        writer.write(f)


def main() -> None:
    settings = get_settings()
    data_dir = settings.get_resolved_data_dir()
    notes_file = data_dir / "afl_notes.txt"
    notes_file.write_text(
        "AFL Notes on Functional Programming:\n"
        "In lambda calculus and modern programming languages, a lambda closure is a first-class function "
        "that bundles its code together with references to variables in its surrounding lexical environment scope. "
        "This allows the closure to access and capture those variables even when invoked outside of their original scope.\n"
        "AFL Rule 42: Closures retain lexical bindings by reference or by value depending on the memory model.",
        encoding="utf-8",
    )

    km = KnowledgeManager(settings=settings)
    km.initialize()

    # Index document
    index_res = km.index_file(notes_file)
    print(f"Indexing result: indexed={index_res.documents_indexed}, skipped={index_res.documents_skipped}, chunks={index_res.chunks_created}")

    # Set up agent with Ollama and tools (longer timeout for 30b model cold start)
    client = OllamaClient(
        base_url=settings.ollama_base_url,
        timeout=240.0,
        default_model="qwen3:30b",
    )


    registry = ToolRegistry()
    registry.register(SearchKnowledgeTool(knowledge_manager=km, settings=settings))
    registry.register(ListIndexedDocumentsTool(knowledge_manager=km, settings=settings))

    perm_mgr = PermissionManager(confirmation_manager=ConfirmationManager(AutoApproveProvider()))
    conv = Conversation()
    agent = Agent(
        conversation=conv,
        client=client,
        registry=registry,
        permission_manager=perm_mgr,
        settings=settings,
    )

    # Test Query 1: AFL notes on lambda closure
    prompt = "What does my AFL notes say about lambda closure?"
    print(f"\nUser: {prompt}")
    print("Assistant: ", end="", flush=True)
    reply = agent.run(prompt, model="qwen3:30b")
    print(reply)

    # Test Query 2: Unrelated topic to verify honest no-hit behavior
    prompt_nohit = "What does my knowledge base say about the history of the Eiffel Tower?"
    print(f"\nUser: {prompt_nohit}")
    print("Assistant: ", end="", flush=True)
    reply_nohit = agent.run(prompt_nohit, model="qwen3:30b")
    print(reply_nohit)


if __name__ == "__main__":
    main()
