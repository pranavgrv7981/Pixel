"""Unit tests for PyInstaller spec file validation and build configuration."""

from pathlib import Path
import pytest

from app.core.config import Settings


def test_spec_file_exists_and_contains_entrypoint() -> None:
    spec_path = Path("build/local_assistant.spec")
    assert spec_path.exists() is True

    content = spec_path.read_text(encoding="utf-8")
    assert "main.py" in content
    assert "LocalAssistant" in content
    assert "PySide6" in content
    assert "app.core" in content
    assert "app.events" in content
    assert "app.models" in content
    assert "app.planning" in content


def test_model_storage_is_external_to_bundle() -> None:
    settings = Settings()
    # Confirm default data dir is external and not inside _MEIPASS
    assert "data" in str(settings.data_dir)
    assert not str(settings.data_dir).startswith("_MEI")
