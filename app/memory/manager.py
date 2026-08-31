"""High-level MemoryManager coordinating repositories, bounded search, and context enrichment."""

import re
from typing import Optional, Union

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.core.logging import get_logger
from app.memory.database import MemoryDatabase
from app.memory.models import (
    MemoryCategory,
    MemoryRecord,
    MemorySource,
)
from app.memory.repository import ConversationRepository, MemoryRepository

logger = get_logger("memory.manager")

# Common English stop words to ignore when extracting deterministic search tokens
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "from", "by", "with", "about", "into",
    "through", "during", "before", "after", "above", "below", "up", "down",
    "what", "where", "when", "why", "how", "who", "which", "whose",
    "my", "your", "his", "her", "its", "our", "their", "me", "you", "him", "us", "them",
    "i", "we", "he", "she", "it", "they", "do", "does", "did", "can", "could",
    "tell", "show", "give", "find", "get", "remember", "recall", "know",
    "this", "that", "these", "those", "and", "or", "but", "not", "of",
}


class MemoryManager:
    """Central manager for conversation persistence and structured long-term memory."""

    def __init__(
        self,
        db: Optional[MemoryDatabase] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db or MemoryDatabase(settings=self.settings)
        self.conversations = ConversationRepository(self.db, settings=self.settings)
        self.memories = MemoryRepository(self.db)

    def initialize(self) -> None:
        """Initialize underlying SQLite database schema idempotently."""
        self.db.initialize()

    def parse_category(self, cat_input: Union[MemoryCategory, str]) -> MemoryCategory:
        """Validate and parse memory category."""
        if isinstance(cat_input, MemoryCategory):
            return cat_input
        if not cat_input or not isinstance(cat_input, str):
            raise ToolValidationError(f"Invalid category '{cat_input}'. Allowed: {[c.value for c in MemoryCategory]}")

        raw = cat_input.strip().upper()
        try:
            return MemoryCategory(raw)
        except ValueError:
            raise ToolValidationError(
                f"Unknown memory category '{cat_input}'. Must be one of: {', '.join(c.value for c in MemoryCategory)}"
            )

    def parse_source(self, src_input: Union[MemorySource, str]) -> MemorySource:
        """Validate and parse memory source."""
        if isinstance(src_input, MemorySource):
            return src_input
        if not src_input or not isinstance(src_input, str):
            return MemorySource.USER

        raw = src_input.strip().lower()
        try:
            return MemorySource(raw)
        except ValueError:
            return MemorySource.USER

    def remember(
        self,
        category: Union[MemoryCategory, str],
        key: str,
        value: str,
        importance: int = 5,
        source: Union[MemorySource, str] = MemorySource.USER,
    ) -> MemoryRecord:
        """Store or update a persistent memory item."""
        cat_enum = self.parse_category(category)
        src_enum = self.parse_source(source)

        if not key or not str(key).strip():
            raise ToolValidationError("Memory key cannot be empty")
        if not value or not str(value).strip():
            raise ToolValidationError("Memory value cannot be empty")

        return self.memories.upsert_memory(
            category=cat_enum,
            key=str(key),
            value=str(value),
            importance=importance,
            source=src_enum,
        )

    def recall(
        self,
        query: Optional[str] = None,
        category: Optional[Union[MemoryCategory, str]] = None,
        limit: Optional[int] = None,
    ) -> list[MemoryRecord]:
        """Recall memories filtered by query keyword and/or category."""
        cat_enum = self.parse_category(category) if category else None
        max_limit = limit or self.settings.max_recalled_memories
        return self.memories.search_memories(query=query, category=cat_enum, limit=max_limit)

    def forget(
        self,
        key: str,
        category: Optional[Union[MemoryCategory, str]] = None,
    ) -> bool:
        """Explicitly forget a memory matching key and optional category."""
        if not key or not str(key).strip():
            raise ToolValidationError("Memory key to forget cannot be empty")
        cat_enum = self.parse_category(category) if category else None
        return self.memories.delete_memory(key=str(key), category=cat_enum)

    def get_relevant_memories(
        self,
        user_query: str,
        limit: Optional[int] = None,
    ) -> list[MemoryRecord]:
        """Retrieve bounded memories relevant to the user query using deterministic keyword matching."""
        if not user_query or not user_query.strip():
            return []

        max_limit = limit or self.settings.max_recalled_memories
        normalized = user_query.lower()
        tokens = re.findall(r"\b[a-z0-9_-]{2,}\b", normalized)

        candidate_keywords = [t for t in tokens if t not in STOP_WORDS]
        if not candidate_keywords:
            return []

        seen_ids: set[str] = set()
        matched: list[MemoryRecord] = []

        # 1. First search with significant keywords
        for word in candidate_keywords:
            results = self.memories.search_memories(query=word, limit=max_limit)
            for rec in results:
                if rec.id not in seen_ids:
                    seen_ids.add(rec.id)
                    matched.append(rec)
                if len(matched) >= max_limit:
                    return matched

        return matched

    def format_memories_for_prompt(self, memories: list[MemoryRecord]) -> str:
        """Format recalled memories into a concise, structured prompt context section."""
        if not memories:
            return ""

        lines = ["[Persistent User Context & Memories]"]
        for m in memories:
            lines.append(f"- [{m.category.value}] {m.key}: {m.value}")
        return "\n".join(lines)
