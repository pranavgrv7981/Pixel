"""Modal dialog prompting user confirmation for medium and high risk tool executions."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.security.permissions import ExecutionContext, SecurityDecision
from app.ui.theme import (
    COLOR_ACCENT,
    COLOR_BG_DARK,
    COLOR_BG_PANEL,
    COLOR_BG_SURFACE,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_WARNING,
)


class ConfirmationDialog(QDialog):
    """Modal confirmation dialog presenting tool risks and parameters for explicit user approval."""

    def __init__(
        self,
        context: ExecutionContext,
        decision: SecurityDecision,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.decision = decision
        self.confirmed = False

        self.setWindowTitle("Security Confirmation Required")
        self.setModal(True)
        self.setFixedWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header with icon and title
        header_layout = QHBoxLayout()
        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(icon_label)

        title_vbox = QVBoxLayout()
        title = QLabel("Action Confirmation Required")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        subtitle = QLabel("An assistant tool is requesting permission to execute.")
        subtitle.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        title_vbox.addWidget(title)
        title_vbox.addWidget(subtitle)
        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Tool Info Card
        info_card = QWidget()
        info_card.setStyleSheet(f"background-color: {COLOR_BG_SURFACE}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 10px;")
        card_layout = QVBoxLayout(info_card)
        card_layout.setSpacing(8)

        tool_row = QHBoxLayout()
        tool_label = QLabel(f"Tool: <b>{context.tool_name}</b>")
        risk_color = COLOR_DANGER if context.risk_level.value == "HIGH" else COLOR_WARNING
        risk_badge = QLabel(f" {context.risk_level.value} RISK ")
        risk_badge.setStyleSheet(f"background-color: {risk_color}; color: #11111b; font-weight: 700; border-radius: 4px; padding: 2px 6px; font-size: 10px;")
        tool_row.addWidget(tool_label)
        tool_row.addStretch()
        tool_row.addWidget(risk_badge)
        card_layout.addLayout(tool_row)

        desc_label = QLabel(f"Reason: {decision.reason}")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        card_layout.addWidget(desc_label)

        layout.addWidget(info_card)

        # Target arguments display
        if context.arguments:
            args_label = QLabel("Parameters:")
            args_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLOR_TEXT_MUTED};")
            layout.addWidget(args_label)

            args_browser = QTextBrowser()
            args_browser.setFixedHeight(70)
            args_browser.setStyleSheet(f"background-color: {COLOR_BG_DARK}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; font-family: Consolas, monospace; font-size: 11px;")
            args_lines = [f"{k} = {v}" for k, v in context.arguments.items()]
            args_browser.setPlainText("\n".join(args_lines))
            layout.addWidget(args_browser)

        # Buttons (Cancel default focus for safety)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel / Deny")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFixedWidth(110)
        self.cancel_btn.clicked.connect(self._handle_deny)
        btn_layout.addWidget(self.cancel_btn)

        self.allow_btn = QPushButton("Allow Execution")
        self.allow_btn.setObjectName("primaryButton")
        self.allow_btn.setCursor(Qt.PointingHandCursor)
        self.allow_btn.setFixedWidth(130)
        self.allow_btn.clicked.connect(self._handle_allow)
        btn_layout.addWidget(self.allow_btn)

        layout.addLayout(btn_layout)

        # Default to Cancel on Enter for safety
        self.cancel_btn.setDefault(True)

    def _handle_allow(self) -> None:
        self.confirmed = True
        self.accept()

    def _handle_deny(self) -> None:
        self.confirmed = False
        self.reject()

    def is_allowed(self) -> bool:
        return self.confirmed
