"""Unit tests for Multimodal Vision data models and representations."""

from datetime import datetime, timezone
import pytest
from app.vision.models import (
    ImageFormat,
    ImageInput,
    ImageSource,
    VisionResult,
    VisionStatus,
)


def test_image_input_initialization():
    """Verify ImageInput initializes with defaults and correctly computes helper properties."""
    img = ImageInput(
        source=ImageSource.FILE,
        path="C:/data/test.png",
        filename="test.png",
        mime_type="image/png",
        image_format=ImageFormat.PNG,
        width=1920,
        height=1080,
        size_bytes=204800,
        sha256_hash="abc123hash",
        base64_data="iVBORw0KGgoAAAANSUhEUg==",
    )

    assert img.source == ImageSource.FILE
    assert img.filename == "test.png"
    assert img.dimensions_str == "1920x1080"
    assert img.size_kb == 200.0
    assert img.is_temp is False
    assert isinstance(img.created_at, datetime)


def test_vision_result_structure():
    """Verify VisionResult holds structured output, timing, and metadata."""
    res = VisionResult(
        text="A line graph showing memory usage over time.",
        model="llava:latest",
        processing_time_seconds=1.45,
        confidence=0.92,
        metadata={"image_count": 1, "dimensions": ["1920x1080"]},
    )

    assert res.text == "A line graph showing memory usage over time."
    assert res.model == "llava:latest"
    assert res.processing_time_seconds == 1.45
    assert res.confidence == 0.92
    assert res.metadata["image_count"] == 1


def test_vision_status_representation():
    """Verify VisionStatus distinguishes between available and unavailable states."""
    status_avail = VisionStatus(
        is_available=True,
        active_model="llava:latest",
        installed_vision_models=["llava:latest", "minicpm-v:latest"],
        error_message=None,
    )
    assert status_avail.is_available is True
    assert status_avail.active_model == "llava:latest"
    assert len(status_avail.installed_vision_models) == 2

    status_unavail = VisionStatus(
        is_available=False,
        active_model=None,
        installed_vision_models=[],
        error_message="No vision-capable local model installed.",
    )
    assert status_unavail.is_available is False
    assert status_unavail.active_model is None
    assert "No vision-capable" in status_unavail.error_message
