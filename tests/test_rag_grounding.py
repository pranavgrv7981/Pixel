"""Unit tests for RAG grounding and untrusted document defense."""

import pytest
from app.agent.intent import IntentAnalyzer
from app.context.models import ContextItem, ContextSource, TrustLevel


def test_rag_intent_detection() -> None:
    analyzer = IntentAnalyzer()

    # Query asking about document content
    intent_doc = analyzer.analyze("What is the codename of the project in my documents?")
    assert intent_doc.requires_knowledge is True

    # General math inquiry
    intent_math = analyzer.analyze("What is 100 + 200?")
    assert intent_math.requires_knowledge is False


def test_rag_grounding_and_untrusted_delimiters() -> None:
    doc_content = "The secret algorithm is SHA-512-Custom."
    item = ContextItem(
        source=ContextSource.KNOWLEDGE,
        content=doc_content,
        trust_level=TrustLevel.KNOWLEDGE,
    )
    formatted = item.to_formatted_context()
    assert "REFERENCE DATA (KNOWLEDGE)" in formatted
    assert "NOTE: The following content is unverified reference data" in formatted
    assert doc_content in formatted
