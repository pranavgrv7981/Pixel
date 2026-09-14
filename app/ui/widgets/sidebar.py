"""Conversation sidebar widget providing Pixel session management, live search, and host telemetry."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.models import ConversationItem
from app.ui.theme import (
    COLOR_ACCENT,
    COLOR_BG_PANEL,
    COLOR_BG_SURFACE,
    COLOR_BORDER_SOLID,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_WHITE,
)


class ConversationSidebar(QWidget):
    """Collapsible sidebar for session management, conversation search, and live host telemetry."""

    new_chat_clicked = Signal()
    conversation_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(270)
        self._raw_items: list[ConversationItem] = []
        self._active_id: Optional[str] = None

        self.setStyleSheet(f"""
            ConversationSidebar {{
                background-color: {COLOR_BG_PANEL};
                border-right: 1px solid {COLOR_BORDER_SOLID};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(12)

        # 1. Header: Branding & Online Status
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)

        top_row = QHBoxLayout()
        title_label = QLabel("⚡ PIXEL // AI")
        title_label.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {COLOR_ACCENT}; letter-spacing: 1px; font-family: Consolas, monospace;")
        top_row.addWidget(title_label)

        top_row.addStretch()

        status_badge = QLabel("● ONLINE")
        status_badge.setStyleSheet(f"font-size: 9px; font-weight: 800; color: {COLOR_SUCCESS}; font-family: Consolas, monospace; background-color: rgba(16, 185, 129, 0.12); padding: 2px 6px; border-radius: 4px; border: 1px solid {COLOR_SUCCESS};")
        top_row.addWidget(status_badge)

        header_vbox.addLayout(top_row)

        sub_title = QLabel("PERSONAL AI ASSISTANT")
        sub_title.setStyleSheet(f"font-size: 9px; font-weight: 600; color: {COLOR_TEXT_MUTED}; letter-spacing: 0.6px; font-family: Consolas, monospace;")
        header_vbox.addWidget(sub_title)

        layout.addLayout(header_vbox)

        # 2. + New Conversation Button
        self.new_chat_btn = QPushButton("+ New Session")
        self.new_chat_btn.setObjectName("primaryButton")
        self.new_chat_btn.setCursor(Qt.PointingHandCursor)
        self.new_chat_btn.clicked.connect(self.new_chat_clicked.emit)
        layout.addWidget(self.new_chat_btn)

        # 3. Search Filter Box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter sessions...")
        self.search_input.setFixedHeight(30)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_SOLID};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input)

        # 4. Section Label
        section_label = QLabel("RECENT SESSIONS")
        section_label.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {COLOR_TEXT_MUTED}; letter-spacing: 0.8px; font-family: Consolas, monospace;")
        layout.addWidget(section_label)

        # 5. Conversation List Widget
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        # 6. Live Host Resource Gauges (Bottom Box)
        resource_box = QWidget()
        resource_box.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_SOLID};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        res_layout = QVBoxLayout(resource_box)
        res_layout.setContentsMargins(8, 8, 8, 8)
        res_layout.setSpacing(6)

        res_title = QLabel("HOST TELEMETRY")
        res_title.setStyleSheet(f"font-size: 9px; font-weight: 800; color: {COLOR_TEXT_MUTED}; font-family: Consolas, monospace; letter-spacing: 0.5px;")
        res_layout.addWidget(res_title)

        # CPU Meter Row
        cpu_row = QHBoxLayout()
        cpu_lbl = QLabel("CPU:")
        cpu_lbl.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY}; font-family: Consolas, monospace;")
        self.cpu_val_lbl = QLabel("0%")
        self.cpu_val_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {COLOR_ACCENT}; font-family: Consolas, monospace;")
        cpu_row.addWidget(cpu_lbl)
        cpu_row.addStretch()
        cpu_row.addWidget(self.cpu_val_lbl)
        res_layout.addLayout(cpu_row)

        self.cpu_bar = QProgressBar()
        self.cpu_bar.setFixedHeight(4)
        self.cpu_bar.setTextVisible(False)
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setValue(0)
        self.cpu_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #080a10;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT};
                border-radius: 2px;
            }}
        """)
        res_layout.addWidget(self.cpu_bar)

        # RAM Meter Row
        ram_row = QHBoxLayout()
        ram_lbl = QLabel("RAM:")
        ram_lbl.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY}; font-family: Consolas, monospace;")
        self.ram_val_lbl = QLabel("0%")
        self.ram_val_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: #a855f7; font-family: Consolas, monospace;")
        ram_row.addWidget(ram_lbl)
        ram_row.addStretch()
        ram_row.addWidget(self.ram_val_lbl)
        res_layout.addLayout(ram_row)

        self.ram_bar = QProgressBar()
        self.ram_bar.setFixedHeight(4)
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setValue(0)
        self.ram_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #080a10;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: #a855f7;
                border-radius: 2px;
            }}
        """)
        res_layout.addWidget(self.ram_bar)

        layout.addWidget(resource_box)

    def update_resource_meters(self, cpu_percent: float, ram_percent: float) -> None:
        """Update CPU and RAM mini-gauges in the sidebar."""
        self.cpu_val_lbl.setText(f"{cpu_percent:.1f}%")
        self.cpu_bar.setValue(int(cpu_percent))

        self.ram_val_lbl.setText(f"{ram_percent:.1f}%")
        self.ram_bar.setValue(int(ram_percent))

    def update_conversations(self, items: list[ConversationItem], active_id: Optional[str] = None) -> None:
        """Populate sidebar list with persistent conversation items."""
        self._raw_items = items
        self._active_id = active_id
        self._render_filtered_items()

    def _render_filtered_items(self) -> None:
        """Render items filtered by the search text query."""
        search_query = self.search_input.text().strip().lower()
        self.list_widget.clear()

        for item in self._raw_items:
            if search_query and search_query not in item.title.lower():
                continue

            date_str = item.updated_at.strftime("%b %d, %H:%M")
            display_text = f"💬 {item.title}\n{date_str} • {item.message_count} msgs"
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.UserRole, item.id)
            self.list_widget.addItem(list_item)

            if self._active_id and item.id == self._active_id:
                self.list_widget.setCurrentItem(list_item)

    def _on_search_changed(self, text: str) -> None:
        self._render_filtered_items()

    def set_active_id(self, active_id: str) -> None:
        """Highlight current active conversation in the list."""
        self._active_id = active_id
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == active_id:
                self.list_widget.setCurrentItem(item)
                break

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.UserRole)
        if cid:
            self.conversation_selected.emit(cid)
