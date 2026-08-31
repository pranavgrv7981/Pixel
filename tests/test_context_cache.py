"""Unit tests for ContextCache and invalidation hooks."""

import time
import pytest
from app.context.cache import ContextCache


def test_cache_get_set_ttl() -> None:
    cache = ContextCache(default_ttl=0.1)

    # Set and get
    cache.set("key1", "val1")
    assert cache.get("key1") == "val1"

    # Sleep past TTL
    time.sleep(0.12)
    assert cache.get("key1") is None


def test_cache_invalidation_hooks() -> None:
    cache = ContextCache(default_ttl=60.0)

    cache.set("user_profile", {"name": "Alice"})
    cache.set("active_project", {"name": "ProjectX"})
    cache.set("summary:conv-1", "Summary 1")
    cache.set("summary:conv-2", "Summary 2")

    # Invalidate profile
    cache.invalidate_profile()
    assert cache.get("user_profile") is None
    assert cache.get("active_project") is not None

    # Invalidate conversation 1
    cache.invalidate_conversation("conv-1")
    assert cache.get("summary:conv-1") is None
    assert cache.get("summary:conv-2") is not None

    # Invalidate all
    cache.invalidate_all()
    assert cache.get("active_project") is None
    assert cache.get("summary:conv-2") is None
