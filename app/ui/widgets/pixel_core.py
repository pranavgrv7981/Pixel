"""Central Animated Pixel AI Core widget with 8 distinct fluid states and 60-FPS vector rendering."""

from enum import Enum
import math
import time
from typing import Optional
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from app.ui.animation import is_reduced_motion


class CoreState(str, Enum):
    """The 8 distinct lifecycle visual states of the Pixel AI Core."""

    IDLE = "idle"
    AWAKENING = "awakening"
    LISTENING = "listening"
    THINKING = "thinking"
    RESPONDING = "responding"
    EXECUTING = "executing"
    SUCCESS = "success"
    ERROR = "error"


PixelCoreState = CoreState


class PixelCoreWidget(QWidget):
    """Central animated living core of Pixel, visualizing AI state transitions with fluid particle and waveform motion."""

    state_changed = Signal(str)

    def __init__(self, size: int = 120, state: Optional[CoreState] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self._state: CoreState = state or CoreState.IDLE
        self._phase: float = 0.0
        self._rotation: float = 0.0
        self._audio_level: float = 0.0
        self._target_audio_level: float = 0.0
        self._pulse_scale: float = 1.0
        self._status_text: str = "Ready"
        self._state_transition_t: float = time.perf_counter()

        # Animation Loop Timer (60 FPS ~ 16ms)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    @property
    def current_state(self) -> CoreState:
        return self._state

    def set_state(self, state: CoreState | str, status_text: Optional[str] = None) -> None:
        """Set the active visual state with fluid morphing."""
        if isinstance(state, str):
            try:
                state = CoreState(state.lower())
            except ValueError:
                state = CoreState.IDLE

        if self._state != state:
            self._state = state
            self._state_transition_t = time.perf_counter()
            self.state_changed.emit(state.value)

        if status_text:
            self._status_text = status_text
        self.update()

    def set_audio_level(self, level: float) -> None:
        """Update reactive audio level (0.0 to 1.0) for voice waveforms."""
        self._target_audio_level = max(0.0, min(1.0, level))

    def set_status_text(self, text: str) -> None:
        self._status_text = text
        self.update()

    def _tick(self) -> None:
        """Advance animation phases smoothly."""
        if is_reduced_motion():
            self._phase += 0.01
            self.update()
            return

        dt = 0.016
        self._phase += dt * 2.0
        if self._phase > 1000.0:
            self._phase = 0.0

        # Rotate orbital rings based on state
        if self._state == CoreState.THINKING:
            self._rotation += 4.5
        elif self._state == CoreState.EXECUTING:
            self._rotation += 6.0
        else:
            self._rotation += 1.0

        if self._rotation >= 360.0:
            self._rotation -= 360.0

        # Smooth audio level damping
        self._audio_level += (self._target_audio_level - self._audio_level) * 0.25

        # State-based auto-decay for SUCCESS / AWAKENING
        elapsed_since_trans = time.perf_counter() - self._state_transition_t
        if self._state == CoreState.AWAKENING and elapsed_since_trans > 0.6:
            self.set_state(CoreState.IDLE)
        elif self._state == CoreState.SUCCESS and elapsed_since_trans > 1.2:
            self.set_state(CoreState.IDLE)

        self.update()

    def paintEvent(self, event) -> None:
        """Render high-fidelity 60-FPS vector AI Core."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        base_r = min(w, h) * 0.28

        # Dynamic color palette by state
        if self._state == CoreState.ERROR:
            c_primary = QColor("#ef4444")
            c_secondary = QColor("#f97316")
            c_glow = QColor(239, 68, 68, 60)
        elif self._state == CoreState.LISTENING:
            c_primary = QColor("#00f2fe")
            c_secondary = QColor("#4facfe")
            c_glow = QColor(0, 242, 254, 80)
        elif self._state == CoreState.THINKING:
            c_primary = QColor("#8b5cf6")
            c_secondary = QColor("#ec4899")
            c_glow = QColor(139, 92, 246, 80)
        elif self._state == CoreState.RESPONDING:
            c_primary = QColor("#00f2fe")
            c_secondary = QColor("#a855f7")
            c_glow = QColor(0, 242, 254, 90)
        elif self._state == CoreState.EXECUTING:
            c_primary = QColor("#06b6d4")
            c_secondary = QColor("#3b82f6")
            c_glow = QColor(6, 182, 212, 80)
        elif self._state == CoreState.SUCCESS:
            c_primary = QColor("#10b981")
            c_secondary = QColor("#00f2fe")
            c_glow = QColor(16, 185, 129, 90)
        else:  # IDLE / AWAKENING
            c_primary = QColor("#00f2fe")
            c_secondary = QColor("#8b5cf6")
            c_glow = QColor(0, 242, 254, 45)

        # 1. Ambient Breathing Halo
        breath = 1.0 + 0.08 * math.sin(self._phase * 1.5)
        if self._state == CoreState.RESPONDING:
            breath += 0.12 * math.sin(self._phase * 4.0)

        outer_radius = base_r * 1.8 * breath
        halo_grad = QRadialGradient(cx, cy, outer_radius)
        halo_grad.setColorAt(0.0, c_glow)
        halo_grad.setColorAt(0.6, QColor(c_glow.red(), c_glow.green(), c_glow.blue(), 15))
        halo_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(halo_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), outer_radius, outer_radius)

        # 2. Orbital Energy Rings (Active in THINKING / EXECUTING / IDLE)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._rotation)

        ring_r = base_r * 1.25
        pen_ring = QPen(c_primary, 1.5)
        pen_ring.setStyle(Qt.DashLine if self._state in (CoreState.THINKING, CoreState.EXECUTING) else Qt.SolidLine)
        pen_ring.setColor(QColor(c_primary.red(), c_primary.green(), c_primary.blue(), 120))
        painter.setPen(pen_ring)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), ring_r, ring_r * 0.85)

        if self._state in (CoreState.THINKING, CoreState.EXECUTING):
            painter.rotate(-self._rotation * 2.2)
            pen_ring2 = QPen(c_secondary, 1.2)
            pen_ring2.setColor(QColor(c_secondary.red(), c_secondary.green(), c_secondary.blue(), 160))
            painter.setPen(pen_ring2)
            painter.drawEllipse(QPointF(0, 0), ring_r * 1.15, ring_r * 0.7)

        painter.restore()

        # 3. Waveform Ripples (Active in LISTENING / RESPONDING)
        if self._state in (CoreState.LISTENING, CoreState.RESPONDING):
            painter.save()
            num_waves = 8
            for i in range(num_waves):
                angle = (i / num_waves) * 2 * math.pi + self._phase * 2.0
                wave_amp = (12.0 + 20.0 * self._audio_level) * math.sin(angle * 2.0 + self._phase * 3.0)
                px = cx + (base_r + wave_amp) * math.cos(angle)
                py = cy + (base_r + wave_amp) * math.sin(angle)

                dot_r = 2.2 + 1.8 * self._audio_level
                painter.setBrush(QBrush(c_primary))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(px, py), dot_r, dot_r)
            painter.restore()

        # 4. Central Fluid Energy Sphere
        core_r = base_r * (0.85 + 0.05 * math.sin(self._phase * 2.5))
        core_grad = QRadialGradient(cx - core_r * 0.25, cy - core_r * 0.25, core_r)
        core_grad.setColorAt(0.0, QColor("#ffffff"))
        core_grad.setColorAt(0.35, c_primary)
        core_grad.setColorAt(0.85, c_secondary)
        core_grad.setColorAt(1.0, QColor(c_secondary.red(), c_secondary.green(), c_secondary.blue(), 180))

        painter.setBrush(QBrush(core_grad))
        painter.setPen(QPen(QColor(255, 255, 255, 140), 1.0))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)
