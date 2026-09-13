"""Central motion and animation architecture for Pixel AI assistant."""

import os
from typing import Callable, Optional
from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QWidget

# Standard Animation Timing Constants (Milliseconds)
DUR_FAST: int = 150
DUR_NORMAL: int = 280
DUR_SLOW: int = 500
DUR_BREATHING: int = 2400

# Standard Easing Curves
EASING_OUT: QEasingCurve.Type = QEasingCurve.OutCubic
EASING_IN_OUT: QEasingCurve.Type = QEasingCurve.InOutQuad
EASING_SMOOTH: QEasingCurve.Type = QEasingCurve.OutQuad


def is_reduced_motion() -> bool:
    """Check if reduced motion accessibility mode is requested via environment."""
    return os.environ.get("PIXEL_REDUCED_MOTION", "0").lower() in ("1", "true", "yes")


def fade_in(
    widget: QWidget,
    duration: int = DUR_NORMAL,
    on_complete: Optional[Callable[[], None]] = None,
) -> Optional[QPropertyAnimation]:
    """Smoothly animate widget opacity from 0.0 to 1.0."""
    if is_reduced_motion():
        widget.show()
        if on_complete:
            on_complete()
        return None

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    widget.show()

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(EASING_OUT)

    if on_complete:
        anim.finished.connect(on_complete)

    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def fade_out(
    widget: QWidget,
    duration: int = DUR_NORMAL,
    hide_on_finish: bool = True,
    on_complete: Optional[Callable[[], None]] = None,
) -> Optional[QPropertyAnimation]:
    """Smoothly animate widget opacity from 1.0 to 0.0."""
    if is_reduced_motion():
        if hide_on_finish:
            widget.hide()
        if on_complete:
            on_complete()
        return None

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(effect.opacity() if effect else 1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(EASING_OUT)

    def _finished():
        if hide_on_finish:
            widget.hide()
        if on_complete:
            on_complete()

    anim.finished.connect(_finished)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def slide_up_fade_in(
    widget: QWidget,
    offset_y: int = 16,
    duration: int = DUR_NORMAL,
    duration_ms: Optional[int] = None,
    on_complete: Optional[Callable[[], None]] = None,
) -> Optional[QParallelAnimationGroup]:
    """Animate widget entrance with subtle upward slide and concurrent fade in."""
    dur = duration_ms if duration_ms is not None else duration
    if is_reduced_motion():
        widget.show()
        if on_complete:
            on_complete()
        return None

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    widget.show()

    # Opacity animation
    anim_opacity = QPropertyAnimation(effect, b"opacity")
    anim_opacity.setDuration(dur)
    anim_opacity.setStartValue(0.0)
    anim_opacity.setEndValue(1.0)
    anim_opacity.setEasingCurve(EASING_OUT)

    # Position animation
    orig_pos = widget.pos()
    start_pos = QPoint(orig_pos.x(), orig_pos.y() + offset_y)
    anim_pos = QPropertyAnimation(widget, b"pos")
    anim_pos.setDuration(dur)
    anim_pos.setStartValue(start_pos)
    anim_pos.setEndValue(orig_pos)
    anim_pos.setEasingCurve(EASING_OUT)

    group = QParallelAnimationGroup(widget)
    group.addAnimation(anim_opacity)
    group.addAnimation(anim_pos)

    if on_complete:
        group.finished.connect(on_complete)

    group.start(QPropertyAnimation.DeleteWhenStopped)
    return group


def slide_drawer(
    widget: QWidget,
    show: bool,
    target_width: int,
    duration: int = DUR_NORMAL,
    on_complete: Optional[Callable[[], None]] = None,
) -> Optional[QPropertyAnimation]:
    """Smoothly slide a collapsible side drawer by animating its maximum width."""
    if is_reduced_motion():
        widget.setMaximumWidth(target_width if show else 0)
        widget.setVisible(show)
        if on_complete:
            on_complete()
        return None

    if show:
        widget.show()

    anim = QPropertyAnimation(widget, b"maximumWidth", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.width())
    anim.setEndValue(target_width if show else 0)
    anim.setEasingCurve(EASING_OUT)

    def _finished():
        if not show:
            widget.hide()
        if on_complete:
            on_complete()

    anim.finished.connect(_finished)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def glow_pulse_effect(widget: QWidget, color_hex: str = "#00f2fe", radius: float = 16.0) -> QGraphicsDropShadowEffect:
    """Attach a subtle futuristic glow shadow effect to a widget."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(radius)
    shadow.setColor(QColor(color_hex))
    shadow.setOffset(0, 0)
    widget.setGraphicsEffect(shadow)
    return shadow
