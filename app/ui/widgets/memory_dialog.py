"""Dialog panel for inspecting and managing persistent user memories."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.memory.manager import MemoryManager
from app.ui.theme import COLOR_BORDER, COLOR_TEXT_MUTED


class MemoryDialog(QDialog):
    """Inspect and manage stored long-term memory records."""

    def __init__(self, memory_manager: MemoryManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.memory_manager = memory_manager
        self.setWindowTitle("Persistent Memories")
        self.resize(600, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel("Persistent User Memories (SQLite assistant.db)")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        layout.addWidget(header)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter memories by key or value...")
        self.search_input.textChanged.connect(self._load_memories)
        layout.addWidget(self.search_input)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Category", "Key", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(f"border: 1px solid {COLOR_BORDER};")
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.forget_btn = QPushButton("Forget Selected")
        self.forget_btn.setObjectName("dangerButton")
        self.forget_btn.clicked.connect(self._forget_selected)
        btn_layout.addWidget(self.forget_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        self._load_memories()

    def _load_memories(self) -> None:
        query = self.search_input.text().strip()
        memories = self.memory_manager.recall(query=query if query else None, limit=50)
        self.table.setRowCount(len(memories))
        for row, m in enumerate(memories):
            cat_item = QTableWidgetItem(m.category.value)
            key_item = QTableWidgetItem(m.key)
            val_item = QTableWidgetItem(m.value)
            cat_item.setFlags(cat_item.flags() ^ Qt.ItemIsEditable)
            key_item.setFlags(key_item.flags() ^ Qt.ItemIsEditable)
            val_item.setFlags(val_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 0, cat_item)
            self.table.setItem(row, 1, key_item)
            self.table.setItem(row, 2, val_item)

    def _forget_selected(self) -> None:
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            key_item = self.table.item(curr_row, 1)
            if key_item:
                key = key_item.text()
                self.memory_manager.forget(key)
                self._load_memories()
