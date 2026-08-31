"""Hybrid knowledge retriever combining dense vector cosine similarity and lexical matching."""

import math
import re
from typing import Optional
import numpy as np

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.index import KnowledgeDatabase
from app.knowledge.models import DocumentChunk, ScoredChunk


class Retriever:
    """Retrieves and ranks relevant document chunks using hybrid search."""

    def __init__(
        self,
        db: KnowledgeDatabase,
        embedding_provider: EmbeddingProvider,
        settings: Optional[Settings] = None,
        vector_weight: float = 0.65,
        lexical_weight: float = 0.35,
    ) -> None:
        self.db = db
        self.embedding_provider = embedding_provider
        self.settings = settings or get_settings()
        self.vector_weight = vector_weight
        self.lexical_weight = lexical_weight
        self.logger = get_logger("knowledge.retriever")

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        filter_path: Optional[str] = None,
        filter_type: Optional[str] = None,
        filter_doc: Optional[str] = None,
    ) -> list[ScoredChunk]:
        """Perform hybrid search over indexed document chunks."""
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        effective_top_k = min(top_k or self.settings.rag_top_k, 20)
        effective_min_score = min_score if min_score is not None else self.settings.rag_min_score

        # 1. Fetch candidate chunks from index
        chunks = self.db.get_all_chunks(filter_path=filter_path, filter_type=filter_type)
        if filter_doc:
            filter_doc_clean = filter_doc.lower().strip()
            chunks = [c for c in chunks if filter_doc_clean in c.file_name.lower() or filter_doc_clean in c.source_path.lower()]

        if not chunks:
            self.logger.debug("No candidate chunks found in index for query '%s'", query)
            return []

        # 2. Compute query embedding vector
        query_vector = np.array(self.embedding_provider.embed_text(cleaned_query), dtype=np.float32)
        query_norm = float(np.linalg.norm(query_vector))
        if query_norm > 0.0:
            query_vector = query_vector / query_norm

        # 3. Tokenize query for lexical scoring
        query_tokens = set(re.findall(r"\b\w+\b", cleaned_query.lower()))

        scored_chunks: list[ScoredChunk] = []

        for chunk in chunks:
            # --- Vector Similarity ---
            vector_score = 0.0
            if chunk.embedding:
                chunk_vector = np.array(chunk.embedding, dtype=np.float32)
                chunk_norm = float(np.linalg.norm(chunk_vector))
                if chunk_norm > 0.0:
                    chunk_vector = chunk_vector / chunk_norm
                    vector_score = float(np.dot(query_vector, chunk_vector))
                    # Clamp between 0.0 and 1.0
                    vector_score = max(0.0, min(1.0, (vector_score + 1.0) / 2.0))

            # --- Lexical Keyword Score ---
            lexical_score = self._compute_lexical_score(chunk.text, query_tokens)

            # --- Combined Hybrid Score ---
            combined = (self.vector_weight * vector_score) + (self.lexical_weight * lexical_score)

            if combined >= effective_min_score:
                scored_chunks.append(
                    ScoredChunk(
                        chunk=chunk,
                        score=round(combined, 4),
                        vector_score=round(vector_score, 4),
                        lexical_score=round(lexical_score, 4),
                    )
                )

        # 4. Sort descending by combined score
        scored_chunks.sort(key=lambda sc: sc.score, reverse=True)

        result = scored_chunks[:effective_top_k]
        self.logger.info("Retrieved %d relevant chunks for query '%s'", len(result), query)
        return result

    def _compute_lexical_score(self, text: str, query_tokens: set[str]) -> float:
        """Compute keyword match ratio and frequency saturation score."""
        if not query_tokens:
            return 0.0

        text_tokens = re.findall(r"\b\w+\b", text.lower())
        if not text_tokens:
            return 0.0

        matched_tokens = 0
        total_freq = 0
        text_token_counts: dict[str, int] = {}
        for t in text_tokens:
            text_token_counts[t] = text_token_counts.get(t, 0) + 1

        for qt in query_tokens:
            count = text_token_counts.get(qt, 0)
            if count > 0:
                matched_tokens += 1
                total_freq += count

        # Ratio of query tokens present in chunk
        coverage_ratio = matched_tokens / len(query_tokens)

        # Frequency saturation bonus
        freq_bonus = math.log1p(total_freq) / 5.0
        raw_score = (0.7 * coverage_ratio) + (0.3 * min(1.0, freq_bonus))

        return max(0.0, min(1.0, raw_score))
