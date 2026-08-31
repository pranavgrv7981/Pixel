"""Embedding provider abstractions and local embedding implementations."""

from abc import ABC, abstractmethod
import hashlib
import math
import re
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolExecutionError
from app.core.ollama_client import OllamaClient


class EmbeddingError(ToolExecutionError):
    """Raised when an embedding operation fails."""


class EmbeddingProvider(ABC):
    """Abstract base class for generating dense vector embeddings."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name or identifier of the embedding model."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensionality of produced embedding vectors."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a single query or text."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of documents."""


class LocalHashEmbeddingProvider(EmbeddingProvider):
    """Deterministic, zero-network, local dense embedding provider using subword n-gram feature hashing.

    Uses character n-grams (3-to-5 chars) and token hashing projected into a dense vector space
    and L2-normalized. Produces high similarity for documents sharing key vocabulary, prefixes,
    technical terms, and phrases, operating completely offline without downloading model weights.
    """

    def __init__(self, dimensions: int = 384, model_name: str = "local-hash-384") -> None:
        self._dimensions = dimensions
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_text(self, text: str) -> list[float]:
        """Compute normalized dense vector for text."""
        vec = [0.0] * self._dimensions
        cleaned = text.lower().strip()
        if not cleaned:
            return vec

        # Extract tokens and character n-grams
        tokens = re.findall(r"\b\w+\b", cleaned)
        features: list[tuple[str, float]] = []

        # Word level features
        for token in tokens:
            features.append((token, 1.0))
            # Subword character n-grams (3, 4, 5)
            if len(token) >= 3:
                for n in (3, 4, 5):
                    for i in range(len(token) - n + 1):
                        features.append((token[i : i + n], 0.5))

        for feat, weight in features:
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dimensions
            sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
            vec[idx] += weight * sign

        # L2 Normalization
        sq_sum = sum(v * v for v in vec)
        if sq_sum > 0.0:
            norm = math.sqrt(sq_sum)
            vec = [v / norm for v in vec]

        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for a list of texts."""
        return [self.embed_text(t) for t in texts]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that calls a local Ollama server running an embedding model."""

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: float = 30.0,
        dimensions: int = 768,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url
        self._timeout = timeout
        self._dimensions = dimensions
        self._client: Optional[OllamaClient] = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self) -> OllamaClient:
        if self._client is None:
            self._client = OllamaClient(
                base_url=self._base_url,
                timeout=self._timeout,
                default_model=self._model_name,
            )
        return self._client

    def embed_text(self, text: str) -> list[float]:
        """Request embedding from Ollama API."""
        try:
            import ollama

            client = ollama.Client(host=self._base_url, timeout=self._timeout)
            response = client.embeddings(model=self._model_name, prompt=text)
            embedding = response.get("embedding", [])
            if not embedding:
                raise EmbeddingError(f"Ollama returned empty embedding for model '{self._model_name}'")
            self._dimensions = len(embedding)
            return embedding
        except Exception as err:
            raise EmbeddingError(f"Failed to generate Ollama embedding: {err}") from err

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings for multiple texts."""
        return [self.embed_text(t) for t in texts]


def get_embedding_provider(settings: Optional[Settings] = None) -> EmbeddingProvider:
    """Instantiate and return the configured EmbeddingProvider."""
    cfg = settings or get_settings()
    provider_type = cfg.embedding_provider.lower().strip()

    if provider_type == "ollama":
        return OllamaEmbeddingProvider(
            model_name=cfg.embedding_model,
            base_url=cfg.ollama_base_url,
            timeout=cfg.ollama_timeout_seconds,
        )

    # Default to deterministic local hash embeddings
    return LocalHashEmbeddingProvider(
        dimensions=384,
        model_name=cfg.embedding_model or "local-hash-384",
    )
