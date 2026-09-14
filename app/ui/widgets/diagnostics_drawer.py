"""Slide-out developer diagnostics and performance panel keeping technical metrics accessible without cluttering the primary UI."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.models import BackendStatus, TurnMetrics
from app.ui.theme import (
    COLOR_ACCENT,
    COLOR_BG_DARK,
    COLOR_BG_PANEL,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PURPLE,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)


class DiagnosticsDrawer(QFrame):
    """Collapsible side drawer housing CPU, RAM, Model routing, RAG, and fine-grained latency telemetry."""

    model_changed = Signal(str)
    model_selected = Signal(str)
    refresh_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._is_open: bool = False
        self.setFixedWidth(300)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #0d101a;
                border-left: 1px solid rgba(255, 255, 255, 0.08);
                font-family: "Segoe UI", Consolas, sans-serif;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("SYSTEM DIAGNOSTICS")
        title.setStyleSheet(f"font-size: 11px; font-weight: 800; letter-spacing: 1px; color: {COLOR_ACCENT};")
        header_layout.addWidget(title)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {COLOR_TEXT_MUTED};
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: #ffffff;
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(close_btn)
        layout.addLayout(header_layout)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(12)

        # 1. Hardware & System Resources
        c_layout.addWidget(self._create_section_label("HARDWARE TELEMETRY"))

        self.cpu_lbl = QLabel("CPU: 0.0%")
        self.cpu_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setFixedHeight(6)
        self.cpu_bar.setTextVisible(False)
        self.cpu_bar.setStyleSheet("QProgressBar { background: #1a1f33; border-radius: 3px; } QProgressBar::chunk { background: #00f2fe; border-radius: 3px; }")

        self.ram_lbl = QLabel("RAM: 0.0%")
        self.ram_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.ram_bar = QProgressBar()
        self.ram_bar.setFixedHeight(6)
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setStyleSheet("QProgressBar { background: #1a1f33; border-radius: 3px; } QProgressBar::chunk { background: #a855f7; border-radius: 3px; }")

        c_layout.addWidget(self.cpu_lbl)
        c_layout.addWidget(self.cpu_bar)
        c_layout.addWidget(self.ram_lbl)
        c_layout.addWidget(self.ram_bar)

        # 2. Ollama & Active Model
        c_layout.addSpacing(6)
        c_layout.addWidget(self._create_section_label("MODEL & ENGINE"))

        self.ollama_status_lbl = QLabel("Ollama: Connected")
        self.ollama_status_lbl.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 11px;")
        c_layout.addWidget(self.ollama_status_lbl)

        model_select_row = QHBoxLayout()
        model_lbl = QLabel("Active:")
        model_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #141829;
                border: 1px solid #232840;
                border-radius: 6px;
                color: #e2e8f0;
                padding: 4px 8px;
                font-size: 11px;
            }
        """)
        self.model_combo.currentTextChanged.connect(self.model_changed.emit)
        self.model_combo.currentTextChanged.connect(self.model_selected.emit)
        model_select_row.addWidget(model_lbl)
        model_select_row.addWidget(self.model_combo)
        c_layout.addLayout(model_select_row)

        self.tier_lbl = QLabel("Tier: FAST_MODEL")
        self.tier_lbl.setStyleSheet(f"color: #00f2fe; font-size: 11px; font-weight: bold;")
        c_layout.addWidget(self.tier_lbl)

        # 3. Last Turn Telemetry Breakdown
        c_layout.addSpacing(6)
        c_layout.addWidget(self._create_section_label("LAST TURN LATENCY"))

        self.ttft_val = QLabel("TTFT: --")
        self.ttft_val.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.gen_speed_val = QLabel("Speed: -- tok/s")
        self.gen_speed_val.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.total_time_val = QLabel("Total: --")
        self.total_time_val.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")

        c_layout.addWidget(self.ttft_val)
        c_layout.addWidget(self.gen_speed_val)
        c_layout.addWidget(self.total_time_val)

        # 4. Agent Capabilities & Storage
        c_layout.addSpacing(6)
        c_layout.addWidget(self._create_section_label("CAPABILITIES & MEMORY"))

        self.tools_count_lbl = QLabel("Tools Loaded: 69")
        self.tools_count_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.rag_docs_lbl = QLabel("Knowledge Docs: 0")
        self.rag_docs_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.memory_count_lbl = QLabel("Memories: Ready")
        self.memory_count_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")

        c_layout.addWidget(self.tools_count_lbl)
        c_layout.addWidget(self.rag_docs_lbl)
        c_layout.addWidget(self.memory_count_lbl)

        # 5. Build & Version Identifier
        c_layout.addSpacing(6)
        c_layout.addWidget(self._create_section_label("BUILD IDENTIFIER"))
        from app.core.config import get_build_commit
        self.build_lbl = QLabel(f"Pixel build: {get_build_commit()}")
        self.build_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-family: Consolas, monospace;")
        c_layout.addWidget(self.build_lbl)

        c_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _create_section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 9px; font-weight: 800; letter-spacing: 0.8px;")
        return lbl

    def update_telemetry(self, metrics: TurnMetrics) -> None:
        """Update latency and token generation metrics."""
        ttft_str = f"{metrics.ttft:.2f}s" if metrics.ttft is not None else "--"
        self.ttft_val.setText(f"TTFT: {ttft_str}")
        self.gen_speed_val.setText(f"Speed: {metrics.tokens_per_second:.1f} tok/s")
        self.total_time_val.setText(f"Total: {metrics.total_time:.2f}s ({metrics.chunks_count} chunks)")
        self.tier_lbl.setText(f"Tier: {metrics.tier or 'STANDARD'}")

    def update_turn_metrics(self, metrics: TurnMetrics) -> None:
        """Alias for update_telemetry."""
        self.update_telemetry(metrics)

    def update_resources(self, cpu_pct: float, ram_pct: float) -> None:
        """Update CPU/RAM bars."""
        self.cpu_lbl.setText(f"CPU: {cpu_pct:.1f}%")
        self.cpu_bar.setValue(int(cpu_pct))
        self.ram_lbl.setText(f"RAM: {ram_pct:.1f}%")
        self.ram_bar.setValue(int(ram_pct))

    def update_backend_status(self, status: Any) -> None:
        """Update Ollama models and connection state."""
        ollama_conn = getattr(status, "ollama_connected", False) or getattr(status, "is_ollama_connected", False)
        if ollama_conn:
            self.ollama_status_lbl.setText("Ollama: Connected ●")
            self.ollama_status_lbl.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 11px;")
        else:
            self.ollama_status_lbl.setText("Ollama: Offline ●")
            self.ollama_status_lbl.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 11px;")

        # Update available models in combo
        avail = getattr(status, "available_models", [])
        if avail:
            current = self.model_combo.currentText()
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            for m in avail:
                self.model_combo.addItem(m)
            sel = getattr(status, "model_name", "") or getattr(status, "selected_model", "")
            if current and current in avail:
                self.model_combo.setCurrentText(current)
            elif sel and sel in avail:
                self.model_combo.setCurrentText(sel)
            self.model_combo.blockSignals(False)

        tools = getattr(status, "tools_count", None) or getattr(status, "tool_count", 69)
        docs = getattr(status, "docs_count", None) or getattr(status, "document_count", 0)
        self.tools_count_lbl.setText(f"Tools Loaded: {tools}")
        self.rag_docs_lbl.setText(f"Knowledge Docs: {docs}")

    @property
    def is_open(self) -> bool:
        return self._is_open

    def set_open(self, open_state: bool) -> None:
        self._is_open = open_state
        self.setVisible(open_state)
