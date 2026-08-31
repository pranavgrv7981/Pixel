"""Deterministic token estimation and relevance scoring engine for context candidates."""

import math
import re
from typing import Optional

from app.context.models import (
    ContextItem,
    ContextSource,
    ProjectContext,
    TrustLevel,
)

# Common stopwords ignored for keyword extraction
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "from", "by", "with", "about", "into",
    "through", "during", "before", "after", "above", "below", "up", "down",
    "what", "where", "when", "why", "how", "who", "which", "whose",
    "my", "your", "his", "her", "its", "our", "their", "me", "you", "him", "us", "them",
    "i", "we", "he", "she", "it", "they", "do", "does", "did", "can", "could", "will", "would",
    "tell", "show", "give", "find", "get", "remember", "recall", "know", "please",
    "this", "that", "these", "those", "and", "or", "but", "not", "of", "as", "if",
}

SYSTEM_KEYWORDS = {
    "ram", "memory", "cpu", "processor", "battery", "uptime", "hardware",
    "system", "specs", "disk", "storage", "performance", "usage", "load", "status",
}


def estimate_tokens(text: str) -> int:
    """Deterministic token estimation.

    Approximates token count without external tokenizer dependencies.
    Average ratio for English/code is approximately 3.8 to 4.0 characters per token,
    with a minimum of 1 token for non-empty text.
    """
    if not text:
        return 0
    clean = text.strip()
    if not clean:
        return 0
    # Base estimation: ~4 chars per token with word boundary awareness
    words = clean.split()
    chars = len(clean)
    approx = max(len(words), math.ceil(chars / 3.8))
    return approx


def extract_keywords(text: str) -> set[str]:
    """Extract normalized alphanumeric keyword tokens excluding common stopwords."""
    if not text:
        return set()
    tokens = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower())
    return {t for t in tokens if t not in STOP_WORDS and not t.isdigit()}


class ContextRanker:
    """Scores candidate context items for semantic and positional relevance to the active query."""

    def __init__(self) -> None:
        pass

    def estimate_item_tokens(self, item: ContextItem) -> int:
        """Estimate and update token count on a ContextItem."""
        tokens = estimate_tokens(item.content)
        item.estimated_tokens = tokens
        return tokens

    def is_system_query(self, query: str) -> bool:
        """Check whether the user query is asking for hardware or system metrics."""
        query_words = extract_keywords(query)
        return bool(query_words.intersection(SYSTEM_KEYWORDS))

    def score_relevance(
        self,
        query: str,
        item: ContextItem,
        active_project: Optional[ProjectContext] = None,
    ) -> float:
        """Compute a normalized relevance score (0.0 to 1.0) for a context item against query."""
        # 1. Mandatory items always receive maximum relevance
        if item.is_mandatory or item.source == ContextSource.CURRENT_MESSAGE:
            return 1.0

        query_norm = query.strip().lower()
        content_norm = item.content.strip().lower()
        if not query_norm or not content_norm:
            return 0.0

        score = 0.0

        # 2. Base score by Source Category
        base_source_weights = {
            ContextSource.TOOL_RESULT: 0.85,
            ContextSource.PLAN: 0.80,
            ContextSource.TASK: 0.70,
            ContextSource.MEMORY: 0.65,
            ContextSource.KNOWLEDGE: 0.60,
            ContextSource.RECENT_CONVERSATION: 0.55,
            ContextSource.PROJECT_CONTEXT: 0.50,
            ContextSource.CONVERSATION_SUMMARY: 0.40,
            ContextSource.USER_PROFILE: 0.35,
            ContextSource.SYSTEM: 0.10,
            ContextSource.BROWSER: 0.50,
        }
        score += base_source_weights.get(item.source, 0.30)

        # 3. System source special gating
        if item.source == ContextSource.SYSTEM:
            if self.is_system_query(query):
                score += 0.75  # Boost strongly if user specifically asked about system/RAM/CPU
            else:
                return 0.0  # Zero out completely if unrelated to system

        # 4. Exact phrase matching boost
        if len(query_norm) > 4 and query_norm in content_norm:
            score += 0.30

        # 5. Keyword overlap scoring
        query_kw = extract_keywords(query)
        content_kw = extract_keywords(item.content)
        if query_kw and content_kw:
            overlap = query_kw.intersection(content_kw)
            overlap_ratio = len(overlap) / len(query_kw)
            score += overlap_ratio * 0.40

        # 6. Active project boost
        if active_project:
            proj_name = active_project.project_name.lower()
            if proj_name in query_norm or proj_name in content_norm:
                score += 0.20
            if item.source == ContextSource.PROJECT_CONTEXT:
                if any(kw in query_norm for kw in ("project", "workspace", "codebase", "app", "root", proj_name)):
                    score += 0.35

        # 7. Trust boundary adjustment (Penalize unverified browser/web data slightly)
        if item.trust_level == TrustLevel.BROWSER:
            score *= 0.90

        # 8. Clamp final score to [0.0, 1.0]
        final_score = max(0.0, min(1.0, score))
        item.relevance_score = round(final_score, 4)
        return item.relevance_score

    def rank_candidates(
        self,
        query: str,
        candidates: list[ContextItem],
        active_project: Optional[ProjectContext] = None,
    ) -> list[ContextItem]:
        """Score all candidates and return them ordered by priority and relevance."""
        for item in candidates:
            self.estimate_item_tokens(item)
            self.score_relevance(query, item, active_project=active_project)

        # Sort criteria:
        # 1. is_mandatory (True first)
        # 2. Priority ascending (1 is highest priority tier)
        # 3. Relevance score descending
        # 4. Created_at descending
        return sorted(
            candidates,
            key=lambda x: (
                not x.is_mandatory,
                x.priority,
                -x.relevance_score,
                -x.created_at.timestamp(),
            ),
        )
