"""Regression tests verifying Settings consistency across subsystems."""

from app.core.config import Settings, get_settings


def test_settings_num_ctx_bounded_for_ram():
    """Verify default num_ctx is bounded to 4096 or less to prevent OOM."""
    settings = Settings()
    assert settings.ollama_num_ctx <= 4096


def test_settings_singleton_consistency():
    """Verify get_settings returns consistent settings instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1.ollama_num_ctx == s2.ollama_num_ctx
    assert s1.ollama_timeout_seconds == s2.ollama_timeout_seconds
