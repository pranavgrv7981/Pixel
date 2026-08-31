"""Pytest fixtures for testing."""

import os
from pathlib import Path
from typing import Generator

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    """Clear lru_cache for get_settings before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Provide an isolated temporary directory simulating project root."""
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def isolated_settings(temp_project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Create a Settings instance isolated to temporary directories."""
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("LOGS_DIR", raising=False)

    settings = Settings(
        project_root=temp_project_dir,
        data_dir=temp_project_dir / "data",
        logs_dir=temp_project_dir / "logs",
        log_to_file=True,
        log_to_console=False,
    )
    return settings


@pytest.fixture(scope="session")
def qapp() -> Generator:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
