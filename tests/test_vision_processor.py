"""Unit tests for ImageProcessor validation, format detection, downscaling, and size bounds."""

import os
import tempfile
import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from app.core.config import Settings
from app.core.exceptions import ToolValidationError
from app.vision.models import ImageFormat, ImageInput, ImageSource
from app.vision.processor import ImageProcessor


def _generate_test_image_bytes(width: int, height: int, fmt: str = "PNG", color: str = "blue") -> bytes:
    """Helper creating raw image bytes via QImage."""
    qimg = QImage(width, height, QImage.Format_RGB32)
    qimg.fill(QColor(color))
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    qimg.save(buffer, fmt)
    data = bytes(byte_array.data())
    buffer.close()
    return data


def test_detect_format():
    """Verify ImageProcessor correctly identifies image headers."""
    processor = ImageProcessor()

    png_bytes = _generate_test_image_bytes(50, 50, "PNG")
    jpg_bytes = _generate_test_image_bytes(50, 50, "JPEG")
    bmp_bytes = _generate_test_image_bytes(50, 50, "BMP")

    assert processor.detect_format(png_bytes) == ImageFormat.PNG
    assert processor.detect_format(jpg_bytes) == ImageFormat.JPEG
    assert processor.detect_format(bmp_bytes) == ImageFormat.BMP
    assert processor.detect_format(b"GARBAGE_HEADER_DATA_1234") == ImageFormat.UNKNOWN
    assert processor.detect_format(b"") == ImageFormat.UNKNOWN


def test_validate_and_process_valid_png():
    """Verify successful processing and metadata generation for a valid PNG."""
    processor = ImageProcessor()
    png_bytes = _generate_test_image_bytes(300, 200, "PNG", color="green")

    result = processor.validate_and_process(
        image_bytes=png_bytes,
        source=ImageSource.FILE,
        filename="green.png",
    )

    assert result.source == ImageSource.FILE
    assert result.filename == "green.png"
    assert result.width == 300
    assert result.height == 200
    assert result.image_format == ImageFormat.PNG
    assert result.mime_type == "image/png"
    assert len(result.sha256_hash) == 64
    assert result.base64_data is not None
    assert len(result.base64_data) > 0


def test_reject_oversized_bytes():
    """Verify images exceeding MAX_IMAGE_BYTES are rejected with ToolValidationError."""
    settings = Settings(max_image_bytes=50)  # very small 50 byte limit for test
    processor = ImageProcessor(settings=settings)
    png_bytes = _generate_test_image_bytes(100, 100, "PNG")

    with pytest.raises(ToolValidationError) as exc:
        processor.validate_and_process(png_bytes)
    assert "exceeds maximum limit" in str(exc.value)


def test_reject_unsupported_or_corrupt_data():
    """Verify corrupted or invalid image payloads are rejected."""
    processor = ImageProcessor()

    with pytest.raises(ToolValidationError) as exc1:
        processor.validate_and_process(b"")
    assert "cannot be empty" in str(exc1.value)

    with pytest.raises(ToolValidationError) as exc2:
        processor.validate_and_process(b"not an image at all but some text payload")
    assert "Unsupported or corrupted" in str(exc2.value)


def test_smooth_downscaling_large_image():
    """Verify large images exceeding image_downscale_max_dim are smoothly downscaled."""
    settings = Settings(
        image_downscale_max_dim=400,
        max_image_pixels=4000 * 4000,
        max_image_bytes=50 * 1024 * 1024,
    )
    processor = ImageProcessor(settings=settings)
    large_bytes = _generate_test_image_bytes(800, 600, "PNG")

    result = processor.validate_and_process(large_bytes)
    assert result.width == 400
    assert result.height == 300  # preserves 4:3 aspect ratio
    assert result.dimensions_str == "400x300"


def test_cleanup_temp_file():
    """Verify cleanup_temp_file safely removes temporary files marked is_temp=True."""
    processor = ImageProcessor()

    fd, path = tempfile.mkstemp(suffix=".png")
    os.write(fd, _generate_test_image_bytes(50, 50, "PNG"))
    os.close(fd)

    assert os.path.exists(path)

    img_input = ImageInput(
        source=ImageSource.SCREENSHOT,
        path=path,
        is_temp=True,
    )

    processor.cleanup_temp_file(img_input)
    assert not os.path.exists(path)
