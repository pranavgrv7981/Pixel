"""Automation Center dialog for managing real-time triggers, master switch, and event history."""

from datetime import datetime, timezone
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.exceptions import TriggerError
from app.events.models import EventType, Trigger, TriggerActionType, TriggerStatus
from app.ui.automation_controller import AutomationController
from app.ui.task_controller import TaskController
from app.ui.widgets.tasks_dialog import NewTaskDialog
from app.ui.theme import (
    COLOR_ACCENT,
    COLOR_BG_PANEL,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_WARNING,
)


class NewTriggerDialog(QDialog):
    """Modal for creating a new real-time event trigger."""

    def __init__(self, automation_controller: AutomationController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.automation_controller = automation_controller
        self.setWindowTitle("Create Event Trigger")
        self.setFixedWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel("New Background Automation Trigger")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. New PDF detector")
        form.addRow("Trigger Name:", self.name_input)

        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "File Created (e.g. *.pdf)",
            "File Modified",
            "System RAM Threshold (>= 90%)",
            "System CPU Threshold (>= 90%)",
            "Application Started",
            "Application Stopped",
        ])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Event Type:", self.type_combo)

        # Dynamic options
        self.pattern_input = QLineEdit("*.pdf")
        self.pattern_input.setPlaceholderText("e.g. *.pdf, *.txt")
        form.addRow("File Pattern:", self.pattern_input)

        self.app_name_input = QLineEdit("code")
        self.app_name_input.setPlaceholderText("e.g. code, notepad")
        self.app_name_input.setVisible(False)
        form.addRow("Application:", self.app_name_input)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(10, 100)
        self.threshold_spin.setValue(90)
        self.threshold_spin.setSuffix("%")
        self.threshold_spin.setVisible(False)
        form.addRow("Threshold:", self.threshold_spin)

        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Notification message or prompt to process...")
        self.prompt_input.setFixedHeight(70)
        form.addRow("Action Content:", self.prompt_input)

        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(5, 3600)
        self.cooldown_spin.setValue(300)
        self.cooldown_spin.setSuffix(" seconds")
        form.addRow("Cooldown:", self.cooldown_spin)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.create_btn = QPushButton("Create Trigger")
        self.create_btn.setObjectName("primaryButton")
        self.create_btn.clicked.connect(self._create_trigger)
        btn_layout.addWidget(self.create_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _on_type_changed(self, idx: int) -> None:
        is_file = idx in (0, 1)
        is_metric = idx in (2, 3)
        is_app = idx in (4, 5)

        self.pattern_input.setVisible(is_file)
        self.threshold_spin.setVisible(is_metric)
        self.app_name_input.setVisible(is_app)

    def _create_trigger(self) -> None:
        name = self.name_input.text().strip()
        prompt = self.prompt_input.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please provide a trigger name.")
            return
        if not prompt:
            prompt = name

        idx = self.type_combo.currentIndex()
        conditions: dict = {}

        if idx == 0:
            ev_type = EventType.FILE_CREATED
            conditions["pattern"] = self.pattern_input.text().strip() or "*.pdf"
        elif idx == 1:
            ev_type = EventType.FILE_MODIFIED
            conditions["pattern"] = self.pattern_input.text().strip() or "*"
        elif idx == 2:
            ev_type = EventType.SYSTEM_THRESHOLD
            conditions["metric"] = "ram"
            conditions["operator"] = ">="
            conditions["value"] = float(self.threshold_spin.value())
        elif idx == 3:
            ev_type = EventType.SYSTEM_THRESHOLD
            conditions["metric"] = "cpu"
            conditions["operator"] = ">="
            conditions["value"] = float(self.threshold_spin.value())
        elif idx == 4:
            ev_type = EventType.PROCESS_STARTED
            conditions["application"] = self.app_name_input.text().strip() or "code"
        else:
            ev_type = EventType.PROCESS_STOPPED
            conditions["application"] = self.app_name_input.text().strip() or "code"

        try:
            trigger = Trigger(
                name=name,
                event_type=ev_type,
                conditions=conditions,
                action_type=TriggerActionType.NOTIFY_USER,
                action_payload={"prompt": prompt},
                cooldown_seconds=self.cooldown_spin.value(),
            )
            self.automation_controller.event_engine.repository.create_trigger(trigger)
            self.accept()
        except Exception as err:
            QMessageBox.warning(self, "Error", f"Failed to create trigger: {err}")


class AutomationDialog(QDialog):
    """Central Automation Center dialog exposing event triggers, scheduled tasks, and activity."""

    def __init__(
        self,
        automation_controller: AutomationController,
        task_controller: Optional[TaskController] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.automation_controller = automation_controller
        self.task_controller = task_controller
        self.setWindowTitle("Automation Center & Resident Background Engine")
        self.resize(780, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Master Switch Banner
        header_layout = QHBoxLayout()
        self.status_title = QLabel("Automation Status:")
        self.status_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        self.status_badge = QLabel("🟢 ACTIVE")
        self.status_badge.setStyleSheet("font-size: 13px; font-weight: 700; color: #a6e3a1; padding-left: 6px;")

        header_layout.addWidget(self.status_title)
        header_layout.addWidget(self.status_badge)
        header_layout.addStretch()

        self.toggle_switch_btn = QPushButton("Pause Automation")
        self.toggle_switch_btn.clicked.connect(self._toggle_master_switch)
        header_layout.addWidget(self.toggle_switch_btn)
        layout.addLayout(header_layout)

        # Tabs: Event Triggers | Scheduled Tasks | Recent Activity
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._refresh_all)

        # 1. Triggers Tab
        triggers_widget = QWidget()
        trig_layout = QVBoxLayout(triggers_widget)
        trig_layout.setContentsMargins(8, 8, 8, 8)
        trig_top = QHBoxLayout()
        trig_top.addStretch()
        self.new_trigger_btn = QPushButton("+ New Trigger")
        self.new_trigger_btn.setObjectName("primaryButton")
        self.new_trigger_btn.clicked.connect(self._open_new_trigger_dialog)
        trig_top.addWidget(self.new_trigger_btn)
        trig_layout.addLayout(trig_top)

        self.triggers_table = QTableWidget()
        self.triggers_table.setColumnCount(5)
        self.triggers_table.setHorizontalHeaderLabels(["Name", "Event Type", "Status", "Conditions", "Fired"])
        self.triggers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.triggers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.triggers_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.triggers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.triggers_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.triggers_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.triggers_table.setSelectionMode(QTableWidget.SingleSelection)
        self.triggers_table.setEditTriggers(QTableWidget.NoEditTriggers)
        trig_layout.addWidget(self.triggers_table)

        trig_btn_row = QHBoxLayout()
        self.pause_trig_btn = QPushButton("Pause")
        self.pause_trig_btn.clicked.connect(self._pause_selected_trigger)
        trig_btn_row.addWidget(self.pause_trig_btn)

        self.resume_trig_btn = QPushButton("Resume")
        self.resume_trig_btn.clicked.connect(self._resume_selected_trigger)
        trig_btn_row.addWidget(self.resume_trig_btn)

        self.delete_trig_btn = QPushButton("Delete")
        self.delete_trig_btn.setStyleSheet(f"color: {COLOR_DANGER};")
        self.delete_trig_btn.clicked.connect(self._delete_selected_trigger)
        trig_btn_row.addWidget(self.delete_trig_btn)

        trig_btn_row.addStretch()
        trig_layout.addLayout(trig_btn_row)
        self.tabs.addTab(triggers_widget, "Event Triggers")

        # 2. Activity History Tab
        activity_widget = QWidget()
        act_layout = QVBoxLayout(activity_widget)
        act_layout.setContentsMargins(8, 8, 8, 8)
        self.activity_table = QTableWidget()
        self.activity_table.setColumnCount(4)
        self.activity_table.setHorizontalHeaderLabels(["Time", "Event", "Source", "Summary"])
        self.activity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.activity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.activity_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.activity_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.activity_table.setEditTriggers(QTableWidget.NoEditTriggers)
        act_layout.addWidget(self.activity_table)
        self.tabs.addTab(activity_widget, "Recent Activity")

        layout.addWidget(self.tabs)

        # Footer Close / Refresh
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.clicked.connect(self._refresh_all)
        footer_layout.addWidget(self.refresh_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(self.close_btn)
        layout.addLayout(footer_layout)

        self._update_master_switch_ui()
        self._refresh_all()

    def _update_master_switch_ui(self) -> None:
        enabled = self.automation_controller.is_automation_enabled()
        if enabled:
            self.status_badge.setText("🟢 ACTIVE")
            self.status_badge.setStyleSheet("font-size: 13px; font-weight: 700; color: #a6e3a1;")
            self.toggle_switch_btn.setText("Pause Automation")
        else:
            self.status_badge.setText("⏸ PAUSED")
            self.status_badge.setStyleSheet("font-size: 13px; font-weight: 700; color: #f9e2af;")
            self.toggle_switch_btn.setText("Resume Automation")

    def _toggle_master_switch(self) -> None:
        new_state = not self.automation_controller.is_automation_enabled()
        self.automation_controller.set_automation_enabled(new_state)
        self._update_master_switch_ui()

    def _refresh_all(self) -> None:
        self._update_master_switch_ui()
        self._refresh_triggers()
        self._refresh_activity()

    def _refresh_triggers(self) -> None:
        triggers = self.automation_controller.list_triggers()
        self.triggers_table.setRowCount(len(triggers))

        for row, t in enumerate(triggers):
            name_item = QTableWidgetItem(t.name)
            name_item.setData(Qt.UserRole, t.trigger_id)
            type_item = QTableWidgetItem(t.event_type.value)

            status_item = QTableWidgetItem(t.status.value.upper())
            if t.status == TriggerStatus.ACTIVE:
                status_item.setForeground(Qt.green)
            else:
                status_item.setForeground(Qt.yellow)

            cond_str = ", ".join([f"{k}={v}" for k, v in t.conditions.items()]) or "-"
            cond_item = QTableWidgetItem(cond_str)
            count_item = QTableWidgetItem(str(t.trigger_count))

            self.triggers_table.setItem(row, 0, name_item)
            self.triggers_table.setItem(row, 1, type_item)
            self.triggers_table.setItem(row, 2, status_item)
            self.triggers_table.setItem(row, 3, cond_item)
            self.triggers_table.setItem(row, 4, count_item)

    def _refresh_activity(self) -> None:
        records = self.automation_controller.get_recent_events(limit=50)
        self.activity_table.setRowCount(len(records))

        for row, r in enumerate(records):
            time_str = r.timestamp.strftime("%H:%M:%S")
            t_item = QTableWidgetItem(time_str)
            ev_item = QTableWidgetItem(r.event_type.value)
            src_item = QTableWidgetItem(r.source)
            sum_item = QTableWidgetItem(r.summary)

            self.activity_table.setItem(row, 0, t_item)
            self.activity_table.setItem(row, 1, ev_item)
            self.activity_table.setItem(row, 2, src_item)
            self.activity_table.setItem(row, 3, sum_item)

    def _open_new_trigger_dialog(self) -> None:
        dlg = NewTriggerDialog(automation_controller=self.automation_controller, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._refresh_all()

    def _get_selected_trigger_id(self) -> Optional[str]:
        row = self.triggers_table.currentRow()
        if row >= 0:
            item = self.triggers_table.item(row, 0)
            if item:
                return item.data(Qt.UserRole)
        return None

    def _pause_selected_trigger(self) -> None:
        tid = self._get_selected_trigger_id()
        if tid:
            self.automation_controller.pause_trigger(tid)
            self._refresh_triggers()

    def _resume_selected_trigger(self) -> None:
        tid = self._get_selected_trigger_id()
        if tid:
            self.automation_controller.resume_trigger(tid)
            self._refresh_triggers()

    def _delete_selected_trigger(self) -> None:
        tid = self._get_selected_trigger_id()
        if tid:
            ans = QMessageBox.question(self, "Confirm Delete", "Delete this automation trigger?")
            if ans == QMessageBox.Yes:
                self.automation_controller.delete_trigger(tid)
                self._refresh_triggers()
