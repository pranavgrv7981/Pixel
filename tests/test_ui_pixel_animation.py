"""Unit and integration tests for Pixel AI Core vector animations, Diagnostics Drawer, and UI motion system."""

import os
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.animation import (
    DUR_FAST,
    DUR_NORMAL,
    DUR_SLOW,
    fade_in,
    fade_out,
    glow_pulse_effect,
    is_reduced_motion,
    slide_drawer,
    slide_up_fade_in,
)
from app.ui.models import BackendStatus, TurnMetrics
from app.ui.widgets.diagnostics_drawer import DiagnosticsDrawer
from app.ui.widgets.pixel_core import CoreState, PixelCoreState, PixelCoreWidget


def test_reduced_motion_flag(monkeypatch):
    """Verify is_reduced_motion respects environment flag."""
    monkeypatch.setenv("PIXEL_REDUCED_MOTION", "1")
    assert is_reduced_motion() is True

    monkeypatch.setenv("PIXEL_REDUCED_MOTION", "0")
    assert is_reduced_motion() is False


def test_pixel_core_states_and_rendering(qapp: QApplication):
    """Verify PixelCoreWidget transitions through all 8 lifecycle states and renders without error."""
    core = PixelCoreWidget(size=100)
    core.show()

    assert core.current_state == PixelCoreState.IDLE

    # Test all 8 states
    states = [
        PixelCoreState.AWAKENING,
        PixelCoreState.LISTENING,
        PixelCoreState.THINKING,
        PixelCoreState.RESPONDING,
        PixelCoreState.EXECUTING,
        PixelCoreState.SUCCESS,
        PixelCoreState.ERROR,
        PixelCoreState.IDLE,
    ]

    for state in states:
        core.set_state(state)
        assert core.current_state == state
        # Force tick update and repaint
        core._tick()
        core.repaint()

    # Audio level reactivity
    core.set_audio_level(0.75)
    assert core._target_audio_level == 0.75
    core._tick()
    assert core._audio_level > 0.0


def test_diagnostics_drawer_telemetry_and_interactions(qapp: QApplication):
    """Verify DiagnosticsDrawer displays metrics, updates resources, and emits model selections."""
    drawer = DiagnosticsDrawer()
    drawer.show()

    # Initial state
    assert not drawer.is_open
    drawer.set_open(True)
    assert drawer.is_open

    # Turn metrics update
    metrics = TurnMetrics(
        ttft=0.28,
        total_time=1.15,
        tokens_per_second=32.4,
        tier="FAST_MODEL",
    )
    drawer.update_turn_metrics(metrics)
    assert "0.28s" in drawer.ttft_val.text()
    assert "32.4" in drawer.gen_speed_val.text()
    assert "1.15s" in drawer.total_time_val.text()

    # Resource updates
    drawer.update_resources(cpu_pct=42.5, ram_pct=68.0)
    assert "42.5%" in drawer.cpu_lbl.text()
    assert drawer.cpu_bar.value() == 42
    assert "68.0%" in drawer.ram_lbl.text()
    assert drawer.ram_bar.value() == 68

    # Backend status update
    status = BackendStatus(
        ollama_connected=True,
        available_models=["qwen3:4b", "qwen3:30b", "deepseek-r1:8b"],
        model_name="qwen3:4b",
        tools_count=69,
        docs_count=12,
    )
    drawer.update_backend_status(status)
    assert "Connected" in drawer.ollama_status_lbl.text()
    assert drawer.model_combo.count() == 3
    assert drawer.model_combo.currentText() == "qwen3:4b"
    assert "69" in drawer.tools_count_lbl.text()
    assert "12" in drawer.rag_docs_lbl.text()

    # Model selection emission
    emitted = []
    drawer.model_selected.connect(emitted.append)
    drawer.model_combo.setCurrentText("deepseek-r1:8b")
    assert "deepseek-r1:8b" in emitted


def test_animation_helpers(qapp: QApplication):
    """Verify animation utility helpers construct valid PySide6 animations without crash."""
    widget = QWidget()
    widget.resize(100, 100)
    widget.show()

    # Fade in & out
    anim_in = fade_in(widget, duration=50)
    assert anim_in is not None

    anim_out = fade_out(widget, duration=50, hide_on_finish=False)
    assert anim_out is not None

    # Slide up fade in
    anim_slide = slide_up_fade_in(widget, offset_y=10, duration_ms=50)
    assert anim_slide is not None

    # Slide drawer
    anim_drawer = slide_drawer(widget, show=True, target_width=200, duration=50)
    assert anim_drawer is not None

    # Glow pulse effect
    effect = glow_pulse_effect(widget, color_hex="#00f2fe", radius=12.0)
    assert effect is not None
    assert widget.graphicsEffect() is effect
