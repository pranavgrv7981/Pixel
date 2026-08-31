"""Dialog panel for inspecting indexed knowledge documents and triggering indexing."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.knowledge.manager import KnowledgeManager
from app.ui.theme import COLOR_BORDER


class KnowledgeDialog(QDialog):
    """Inspect and manage indexed personal documents in RAG knowledge database."""

    def __init__(self, knowledge_manager: KnowledgeManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.knowledge_manager = knowledge_manager
        self.setWindowTitle("Personal Knowledge / RAG")
        self.resize(650, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Indexed Knowledge Documents (SQLite knowledge.db)")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        layout.addWidget(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File Name", "Type", "Size", "Chunks"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setStyleSheet(f"border: 1px solid {COLOR_BORDER};")
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()

        self.index_file_btn = QPushButton("+ Index File...")
        self.index_file_btn.setObjectName("primaryButton")
        self.index_file_btn.clicked.connect(self._index_file)
        btn_layout.addWidget(self.index_file_btn)

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setObjectName("dangerButton")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        self._load_documents()

    def _load_documents(self) -> None:
        docs = self.knowledge_manager.list_documents()
        self.table.setRowCount(len(docs))
        for row, d in enumerate(docs):
            name_item = QTableWidgetItem(d.file_name)
            type_item = QTableWidgetItem(d.file_type)
            size_kb = f"{d.file_size / 1024:.1f} KB" if d.file_size else "0 KB"
            size_item = QTableWidgetItem(size_kb)
            chunks_item = QTableWidgetItem(str(d.chunk_count))

            for it in (name_item, type_item, size_item, chunks_item):
                it.setFlags(it.flags() ^ Qt.ItemIsEditable)

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, size_item)
            self.table.setItem(row, 3, chunks_item)

    def _index_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Document to Index",
            filter="Documents (*.txt *.md *.pdf *.py *.c *.cpp *.h *.json *.csv);;All Files (*.*)",
        )
        if path:
            self.knowledge_manager.index_file(path)
            self._load_documents()

    def _remove_selected(self) -> None:
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            docs = self.knowledge_manager.list_documents()
            if curr_row < len(docs):
                doc_id = docs[curr_row].id
                self.knowledge_manager.remove_document(doc_id)
                self._load_documents()
