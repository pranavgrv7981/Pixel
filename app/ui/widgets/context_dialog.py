"""Context Inspector dialog for inspecting assembled prompt context, token usage, and source allocations."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.context.models import ContextDiagnostics


class ContextInspectorDialog(QDialog):
    """Developer and diagnostic inspector for active context budgeting and relevance scoring."""

    def __init__(self, diagnostics: Optional[ContextDiagnostics] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Context Inspector — Diagnostics & Token Budget")
        self.setMinimumSize(680, 500)
        self.resize(750, 550)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header overview
        title_label = QLabel("<b>Active Context Assembly Diagnostics</b>")
        title_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(title_label)

        # Metrics overview cards
        metrics_layout = QHBoxLayout()
        self.tokens_card = QLabel("Tokens: 0 / 0")
        self.tokens_card.setStyleSheet("background: #2b2b2b; color: #4CAF50; padding: 8px; border-radius: 6px; font-weight: bold;")
        self.items_card = QLabel("Items: 0 included (0 excluded)")
        self.items_card.setStyleSheet("background: #2b2b2b; color: #2196F3; padding: 8px; border-radius: 6px; font-weight: bold;")
        self.latency_card = QLabel("Assembly Latency: 0.0 ms")
        self.latency_card.setStyleSheet("background: #2b2b2b; color: #FF9800; padding: 8px; border-radius: 6px; font-weight: bold;")

        metrics_layout.addWidget(self.tokens_card)
        metrics_layout.addWidget(self.items_card)
        metrics_layout.addWidget(self.latency_card)
        layout.addLayout(metrics_layout)

        # Breakdown Table
        breakdown_title = QLabel("<b>Source Breakdown & Allocation</b>")
        layout.addWidget(breakdown_title)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Context Source", "Allocated Items"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Warnings / Notices area
        self.warnings_view = QTextEdit()
        self.warnings_view.setReadOnly(True)
        self.warnings_view.setMaximumHeight(80)
        self.warnings_view.setPlaceholderText("No context warnings or degradations.")
        layout.addWidget(self.warnings_view)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        if diagnostics:
            self.set_diagnostics(diagnostics)

    def set_diagnostics(self, diag: ContextDiagnostics) -> None:
        """Populate dialog with diagnostics data."""
        self.tokens_card.setText(f"Estimated Tokens: {diag.estimated_tokens:,} / {diag.budget_tokens:,}")
        self.items_card.setText(f"Items: {diag.included_items_count} included ({diag.excluded_items_count} excluded)")
        self.latency_card.setText(f"Assembly Latency: {diag.latency_ms:.1f} ms")

        self.table.setRowCount(0)
        for src, count in sorted(diag.source_breakdown.items()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(src.replace("_", " ").title()))
            self.table.setItem(row, 1, QTableWidgetItem(str(count)))

        if diag.warnings:
            self.warnings_view.setPlainText("\n".join(f"⚠ {w}" for w in diag.warnings))
        else:
            self.warnings_view.setPlainText("✓ Context budgeted and assembled cleanly without warnings.")
