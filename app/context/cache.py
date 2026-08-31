"""Time-to-live (TTL) memory cache with event-driven invalidation for stable context candidates."""

import time
from typing import Any, Generic, Optional, TypeVar

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("context.cache")

T = TypeVar("T")


class CacheEntry(Generic[T]):
    """Internal wrapper for cached payload and its creation timestamp."""

    def __init__(self, value: T, ttl: float) -> None:
        self.value: T = value
        self.ttl: float = ttl
        self.created_at: float = time.time()

    def is_expired(self) -> bool:
        """Check if the cache entry has exceeded its TTL."""
        return (time.time() - self.created_at) > self.ttl


class ContextCache:
    """Thread-safe in-memory cache for stable context candidates."""

    def __init__(self, default_ttl: Optional[float] = None, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.default_ttl = default_ttl if default_ttl is not None else self.settings.context_cache_ttl_seconds
        self._cache: dict[str, CacheEntry[Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Retrieve cached value if present and unexpired."""
        entry = self._cache.get(key)
        if not entry:
            return None

        if entry.is_expired():
            del self._cache[key]
            logger.debug("Evicted expired context cache key: %s", key)
            return None

        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Store value in cache with specified or default TTL."""
        eff_ttl = ttl if ttl is not None else self.default_ttl
        self._cache[key] = CacheEntry(value=value, ttl=eff_ttl)

    def invalidate(self, key: str) -> bool:
        """Invalidate a specific cache key."""
        if key in self._cache:
            del self._cache[key]
            logger.debug("Invalidated context cache key: %s", key)
            return True
        return False

    def invalidate_profile(self) -> None:
        """Invalidate cached user profile."""
        self.invalidate("user_profile")

    def invalidate_project(self) -> None:
        """Invalidate cached project context."""
        self.invalidate("active_project")

    def invalidate_conversation(self, conversation_id: str) -> None:
        """Invalidate summaries and cached turns for a conversation."""
        keys_to_remove = [k for k in self._cache if k.startswith(f"summary:{conversation_id}") or k.startswith(f"conv:{conversation_id}")]
        for k in keys_to_remove:
            del self._cache[k]
        logger.debug("Invalidated %d cache keys for conversation %s", len(keys_to_remove), conversation_id)

    def invalidate_all(self) -> None:
        """Flush the entire cache."""
        self._cache.clear()
        logger.debug("Context cache flushed completely.")
