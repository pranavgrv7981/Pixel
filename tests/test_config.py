"""Tests for app/core/config.py."""

from pathlib import Path
import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_default_settings() -> None:
    """Verify default configuration values."""
    settings = Settings()
    assert settings.app_name == "Local AI Personal Assistant"
    assert settings.version == "0.1.0"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.log_to_file is True
    assert settings.log_to_console is True
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.default_model in ("qwen3:30b", "llama3")


def test_log_level_case_insensitivity() -> None:
    """Verify log_level validator converts to uppercase."""
    settings = Settings(log_level="debug")
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_raises() -> None:
    """Verify invalid log level raises ValidationError."""
    with pytest.raises(ValidationError):
        Settings(log_level="INVALID_LEVEL")


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify environment variables override default settings."""
    monkeypatch.setenv("APP_NAME", "Custom Assistant")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("DEFAULT_MODEL", "mistral")

    settings = Settings()
    assert settings.app_name == "Custom Assistant"
    assert settings.environment == "production"
    assert settings.log_level == "WARNING"
    assert settings.default_model == "mistral"


def test_ensure_directories(tmp_path: Path) -> None:
    """Verify that ensure_directories creates data and logs directories."""
    data_dir = tmp_path / "custom_data"
    logs_dir = tmp_path / "custom_logs"
    assert not data_dir.exists()
    assert not logs_dir.exists()

    settings = Settings(
        project_root=tmp_path,
        data_dir=data_dir,
        logs_dir=logs_dir,
    )
    settings.ensure_directories()

    assert data_dir.is_dir()
    assert logs_dir.is_dir()


def test_get_settings_cached() -> None:
    """Verify get_settings returns the same cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
