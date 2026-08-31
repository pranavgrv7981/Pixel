"""Expandable widget displaying intermediate tool activity and execution outcomes."""

from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import (
    COLOR_ACCENT,
    COLOR_BG_DARK,
    COLOR_BG_PANEL,
    COLOR_BG_SURFACE,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)


class ToolActivityWidget(QWidget):
    """Holographic HUD card displaying tool execution and telemetry."""

    def __init__(
        self,
        tool_name: str,
        initial_args: Optional[dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.tool_name = tool_name
        self.args = initial_args or {}
        self.is_expanded = False

        self.setStyleSheet(f"""
            QWidget {{
                background-color: #121524;
                border: 1px solid #28304c;
                border-left: 3px solid #00f2fe;
                border-radius: 6px;
            }}
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 6, 10, 6)
        self.main_layout.setSpacing(4)

        # Header Row
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.status_icon = QLabel("⚙")
        self.status_icon.setStyleSheet("color: #00f2fe; font-size: 12px; font-weight: bold;")

        self.name_label = QLabel(f"TOOL: <b>{tool_name}</b>")
        self.name_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 11px; font-family: Consolas, monospace;")

        self.status_label = QLabel("Executing...")
        self.status_label.setStyleSheet(f"color: {COLOR_WARNING}; font-size: 10px; font-family: Consolas, monospace;")

        self.expand_btn = QPushButton("▸")
        self.expand_btn.setFixedSize(18, 18)
        self.expand_btn.setCursor(Qt.PointingHandCursor)
        self.expand_btn.setStyleSheet(f"border: none; background: transparent; color: {COLOR_TEXT_MUTED}; font-size: 10px;")
        self.expand_btn.clicked.connect(self.toggle_expand)

        header.addWidget(self.status_icon)
        header.addWidget(self.name_label)
        header.addWidget(self.status_label)
        header.addStretch()
        header.addWidget(self.expand_btn)
        self.main_layout.addLayout(header)

        # Detail Container (collapsed by default)
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(4, 4, 4, 4)

        self.details_label = QLabel("")
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-family: Consolas, monospace; background-color: #090b12; padding: 6px; border-radius: 4px;")
        self.details_layout.addWidget(self.details_label)

        self.details_widget.setVisible(False)
        self.main_layout.addWidget(self.details_widget)

    def set_finished(self, success: bool, summary: str) -> None:
        """Update display when tool finishes."""
        if success:
            self.status_icon.setText("✓")
            self.status_icon.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; font-weight: bold;")
            self.status_label.setText("Completed")
            self.status_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 10px; font-weight: bold; font-family: Consolas, monospace;")
        else:
            self.status_icon.setText("✗")
            self.status_icon.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 12px; font-weight: bold;")
            self.status_label.setText("Failed")
            self.status_label.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 10px; font-weight: bold; font-family: Consolas, monospace;")

        detail_text = f"Output: {summary}"
        if self.args:
            args_str = ", ".join(f"{k}={v}" for k, v in self.args.items())
            detail_text = f"Input: {args_str}\n{detail_text}"
        self.details_label.setText(detail_text)

    def toggle_expand(self) -> None:
        """Expand or collapse the details pane."""
        self.is_expanded = not self.is_expanded
        self.details_widget.setVisible(self.is_expanded)
        self.expand_btn.setText("▾" if self.is_expanded else "▸")
