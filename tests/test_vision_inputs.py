"""Unit tests for ImageInputLoader handling filesystem files, screenshot permissions, and clipboard data."""

from pathlib import Path
import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from app.core.config import Settings
from app.core.exceptions import SecurityError, ToolValidationError
from app.vision.inputs import ImageInputLoader
from app.vision.models import ImageFormat, ImageSource


def _create_sample_png(file_path: Path, width: int = 100, height: int = 100) -> None:
    """Save sample PNG bytes to disk."""
    qimg = QImage(width, height, QImage.Format_RGB32)
    qimg.fill(QColor("magenta"))
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    qimg.save(buffer, "PNG")
    file_path.write_bytes(bytes(byte_array.data()))
    buffer.close()


def test_load_from_file_valid(tmp_path: Path):
    """Verify loading a valid image file inside configured PathGuard root."""
    test_img = tmp_path / "diagram.png"
    _create_sample_png(test_img, 150, 100)

    settings = Settings(filesystem_allowed_roots=[str(tmp_path)])
    loader = ImageInputLoader(settings=settings)

    img_input = loader.load_from_file(test_img)
    assert img_input.source == ImageSource.FILE
    assert img_input.filename == "diagram.png"
    assert img_input.width == 150
    assert img_input.height == 100
    assert img_input.image_format == ImageFormat.PNG


def test_load_from_file_path_traversal_blocked(tmp_path: Path):
    """Verify PathGuard blocks loading images outside allowed root boundaries."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    forbidden_dir = tmp_path / "forbidden"
    forbidden_dir.mkdir()

    secret_img = forbidden_dir / "secret.png"
    _create_sample_png(secret_img, 50, 50)

    settings = Settings(filesystem_allowed_roots=[str(allowed_dir)])
    loader = ImageInputLoader(settings=settings)

    with pytest.raises((SecurityError, ToolValidationError)):
        loader.load_from_file(secret_img)


def test_screenshot_disabled_by_default(tmp_path: Path):
    """Verify screenshot capture is blocked fail-closed when allow_screen_capture=False."""
    settings = Settings(allow_screen_capture=False, filesystem_allowed_roots=[str(tmp_path)])
    loader = ImageInputLoader(settings=settings)

    with pytest.raises(SecurityError) as exc:
        loader.capture_screenshot()
    assert "Screen capture is disabled by policy" in str(exc.value)


def test_clipboard_loader_safe_when_empty():
    """Verify clipboard loader returns None or ImageInput without crashing."""
    loader = ImageInputLoader()
    result = loader.load_from_clipboard()
    # In headless/test environment, clipboard is either None or valid ImageInput
    assert result is None or result.source == ImageSource.CLIPBOARD
