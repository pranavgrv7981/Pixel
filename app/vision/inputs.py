"""Input loaders for filesystem images, desktop screenshots, and clipboard buffers."""

import os
from pathlib import Path
import tempfile
from typing import Optional, Union

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication, QImage, QPixmap

from app.core.config import Settings, get_settings
from app.core.exceptions import SecurityError, ToolValidationError
from app.core.logging import get_logger
from app.tools.path_guard import PathGuard
from app.vision.models import ImageInput, ImageSource
from app.vision.processor import ImageProcessor

logger = get_logger("vision.inputs")


class ImageInputLoader:
    """Loads and validates image inputs from local files, screen captures, and clipboard data."""

    def __init__(
        self,
        processor: Optional[ImageProcessor] = None,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.processor = processor or ImageProcessor(settings=self.settings)
        self.path_guard = path_guard or PathGuard(settings=self.settings)

    def load_from_file(self, file_path: Union[str, Path]) -> ImageInput:
        """Load and validate an image from the local filesystem with PathGuard boundary validation."""
        validated_path = self.path_guard.validate_path(file_path, check_exists=True, must_be_file=True)

        try:
            image_bytes = validated_path.read_bytes()
            return self.processor.validate_and_process(
                image_bytes=image_bytes,
                source=ImageSource.FILE,
                filename=validated_path.name,
                original_path=str(validated_path),
                is_temp=False,
            )
        except ToolValidationError:
            raise
        except Exception as err:
            logger.error("Failed to read image file '%s': %s", validated_path.name, err)
            raise ToolValidationError(f"Could not read image file '{validated_path.name}': {err}")

    def capture_screenshot(self, scope: str = "full") -> ImageInput:
        """Capture a one-shot desktop screenshot if permitted by security settings."""
        if not self.settings.allow_screen_capture:
            logger.warning("Screenshot capture rejected: ALLOW_SCREEN_CAPTURE is disabled in configuration.")
            raise SecurityError(
                "Screen capture is disabled by policy. Enable 'ALLOW_SCREEN_CAPTURE=True' in settings to allow screenshots."
            )

        app = QGuiApplication.instance()
        if not app:
            logger.error("Screen capture failed: No active QGuiApplication instance.")
            raise ToolValidationError("Screen capture requires an active graphical desktop session.")

        screen = QGuiApplication.primaryScreen()
        if not screen:
            raise ToolValidationError("No primary display screen detected.")

        pixmap: QPixmap = screen.grabWindow(0)
        if pixmap.isNull():
            raise ToolValidationError("Failed to capture screen buffer from display.")

        # Save to temporary PNG file
        temp_dir = self.settings.get_resolved_data_dir() / "temp_vision"
        temp_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_file_path = tempfile.mkstemp(dir=str(temp_dir), prefix="screenshot_", suffix=".png")
        os.close(fd)

        saved = pixmap.save(temp_file_path, "PNG")
        if not saved:
            raise ToolValidationError("Failed to encode and save screenshot buffer.")

        image_bytes = Path(temp_file_path).read_bytes()
        logger.info("Captured one-shot screenshot (%d bytes, scope=%s)", len(image_bytes), scope)

        return self.processor.validate_and_process(
            image_bytes=image_bytes,
            source=ImageSource.SCREENSHOT,
            filename="screenshot.png",
            original_path=temp_file_path,
            is_temp=True,
        )

    def load_from_clipboard(self) -> Optional[ImageInput]:
        """Read image data from the system clipboard if an image is present."""
        app = QGuiApplication.instance()
        if not app:
            logger.debug("Clipboard check skipped: No active QGuiApplication instance.")
            return None

        clipboard = QGuiApplication.clipboard()
        if not clipboard:
            return None

        image = clipboard.image()
        if image.isNull():
            return None

        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        image_bytes = bytes(byte_array.data())
        buffer.close()

        if not image_bytes:
            return None

        logger.info("Read image from system clipboard (%d bytes)", len(image_bytes))
        return self.processor.validate_and_process(
            image_bytes=image_bytes,
            source=ImageSource.CLIPBOARD,
            filename="clipboard_image.png",
            original_path=None,
            is_temp=False,
        )
