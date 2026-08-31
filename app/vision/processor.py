"""Safe image decoding, format validation, dimension bounding, and preprocessing."""

import base64
import hashlib
import io
import os
from pathlib import Path
import tempfile
from typing import Optional, Union

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

from app.core.config import Settings, get_settings
from app.core.exceptions import ToolValidationError
from app.core.logging import get_logger
from app.vision.models import ImageFormat, ImageInput, ImageSource

logger = get_logger("vision.processor")


class ImageProcessor:
    """Validates and preprocesses image files and raw bytes to enforce size, dimension, and memory bounds."""

    MAGIC_BYTES = {
        ImageFormat.PNG: b"\x89PNG\r\n\x1a\n",
        ImageFormat.JPEG: b"\xff\xd8\xff",
        ImageFormat.BMP: b"BM",
    }

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def detect_format(self, data: bytes) -> ImageFormat:
        """Inspect raw header bytes to identify image format."""
        if not data or len(data) < 8:
            return ImageFormat.UNKNOWN

        if data.startswith(self.MAGIC_BYTES[ImageFormat.PNG]):
            return ImageFormat.PNG
        if data.startswith(self.MAGIC_BYTES[ImageFormat.JPEG]):
            return ImageFormat.JPEG
        if data.startswith(self.MAGIC_BYTES[ImageFormat.BMP]):
            return ImageFormat.BMP
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ImageFormat.WEBP

        return ImageFormat.UNKNOWN

    def validate_and_process(
        self,
        image_bytes: bytes,
        source: ImageSource = ImageSource.FILE,
        filename: str = "image.png",
        original_path: Optional[str] = None,
        is_temp: bool = False,
    ) -> ImageInput:
        """Validate format, size, and dimensions, downscaling if necessary for memory safety.

        Returns:
            Structured ImageInput ready for vision inference.

        Raises:
            ToolValidationError: If image is empty, malformed, unsupported, or exceeds maximum bounds.
        """
        if not image_bytes:
            raise ToolValidationError("Image byte payload cannot be empty.")

        # 1. Byte size limit check
        if len(image_bytes) > self.settings.max_image_bytes:
            raise ToolValidationError(
                f"Image size ({len(image_bytes)} bytes) exceeds maximum limit ({self.settings.max_image_bytes} bytes / {self.settings.max_image_bytes // (1024*1024)} MB)"
            )

        # 2. Header format detection
        fmt = self.detect_format(image_bytes)
        if fmt == ImageFormat.UNKNOWN:
            raise ToolValidationError("Unsupported or corrupted image format. Allowed formats: PNG, JPEG, WEBP, BMP.")

        # 3. Decode into QImage for dimension validation
        qimg = QImage()
        loaded = qimg.loadFromData(image_bytes)
        if not loaded or qimg.isNull():
            raise ToolValidationError("Failed to decode image data: file is corrupted or unreadable.")

        orig_w = qimg.width()
        orig_h = qimg.height()
        total_pixels = orig_w * orig_h

        # 4. Pixel and dimension bounds
        if total_pixels > self.settings.max_image_pixels:
            raise ToolValidationError(
                f"Image resolution ({orig_w}x{orig_h} = {total_pixels} px) exceeds maximum pixel limit ({self.settings.max_image_pixels} px)"
            )

        # 5. Smooth downscaling if image exceeds downscale threshold
        max_dim = self.settings.image_downscale_max_dim
        final_img = qimg
        if orig_w > max_dim or orig_h > max_dim:
            final_img = qimg.scaled(max_dim, max_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logger.info("Downscaled image from %dx%d to %dx%d for memory and context optimization.", orig_w, orig_h, final_img.width(), final_img.height())

        # 6. Convert to PNG bytes for consistent multimodal transport
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        final_img.save(buffer, "PNG")
        processed_bytes = bytes(byte_array.data())
        buffer.close()

        sha256 = hashlib.sha256(processed_bytes).hexdigest()
        b64_str = base64.b64encode(processed_bytes).decode("ascii")

        mime_map = {
            ImageFormat.PNG: "image/png",
            ImageFormat.JPEG: "image/jpeg",
            ImageFormat.WEBP: "image/webp",
            ImageFormat.BMP: "image/bmp",
        }

        return ImageInput(
            source=source,
            path=original_path,
            filename=filename,
            mime_type=mime_map.get(fmt, "image/png"),
            image_format=fmt,
            width=final_img.width(),
            height=final_img.height(),
            size_bytes=len(processed_bytes),
            sha256_hash=sha256,
            base64_data=b64_str,
            is_temp=is_temp,
        )

    def cleanup_temp_file(self, image_input: ImageInput) -> None:
        """Safely delete temporary image file on disk."""
        if image_input.is_temp and image_input.path and os.path.exists(image_input.path):
            try:
                os.unlink(image_input.path)
                logger.debug("Cleaned up temporary image file '%s'", image_input.path)
            except OSError as err:
                logger.warning("Could not delete temporary image file '%s': %s", image_input.path, err)
