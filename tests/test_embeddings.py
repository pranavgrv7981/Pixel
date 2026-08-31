"""Tests for local and Ollama embedding providers."""

import math
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.knowledge.embeddings import (
    EmbeddingError,
    LocalHashEmbeddingProvider,
    OllamaEmbeddingProvider,
    get_embedding_provider,
)


def test_local_hash_embedding_provider_shape_and_normalization() -> None:
    provider = LocalHashEmbeddingProvider(dimensions=384)
    assert provider.dimensions == 384
    assert provider.model_name == "local-hash-384"

    vec = provider.embed_text("Lambda closures in programming languages")
    assert len(vec) == 384

    # Verify L2 normalization (norm should be 1.0)
    norm = math.sqrt(sum(x * x for x in vec))
    assert pytest.approx(norm, 1e-4) == 1.0


def test_local_hash_embedding_deterministic() -> None:
    provider = LocalHashEmbeddingProvider(dimensions=384)
    text = "Deterministic testing of embedding vectors"
    vec1 = provider.embed_text(text)
    vec2 = provider.embed_text(text)
    assert vec1 == vec2


def test_local_hash_batch_embeddings() -> None:
    provider = LocalHashEmbeddingProvider(dimensions=384)
    texts = ["First document", "Second document", "Third document"]
    batch = provider.embed_documents(texts)
    assert len(batch) == 3
    for v in batch:
        assert len(v) == 384


def test_ollama_embedding_provider_success() -> None:
    mock_response = {"embedding": [0.1, 0.2, 0.3, 0.4]}

    with patch("ollama.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.embeddings.return_value = mock_response
        mock_client_cls.return_value = mock_client

        provider = OllamaEmbeddingProvider(model_name="nomic-embed-text")
        vec = provider.embed_text("Test query")
        assert len(vec) == 4
        assert vec == [0.1, 0.2, 0.3, 0.4]


def test_ollama_embedding_provider_error() -> None:
    with patch("ollama.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.embeddings.side_effect = RuntimeError("Server offline")
        mock_client_cls.return_value = mock_client

        provider = OllamaEmbeddingProvider(model_name="nomic-embed-text")
        with pytest.raises(EmbeddingError) as exc_info:
            provider.embed_text("Test query")
        assert "Failed to generate Ollama embedding" in str(exc_info.value)


def test_get_embedding_provider_factory() -> None:
    local_cfg = Settings(embedding_provider="local", embedding_model="local-hash-384")
    p1 = get_embedding_provider(local_cfg)
    assert isinstance(p1, LocalHashEmbeddingProvider)

    ollama_cfg = Settings(embedding_provider="ollama", embedding_model="nomic-embed-text")
    p2 = get_embedding_provider(ollama_cfg)
    assert isinstance(p2, OllamaEmbeddingProvider)
