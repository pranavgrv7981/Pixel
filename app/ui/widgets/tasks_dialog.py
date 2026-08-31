"""Scheduled tasks management dialog and task creation modal."""

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

from app.core.exceptions import TaskError
from app.tasks.models import Task, TaskSchedule, TaskStatus, TaskType
from app.tasks.triggers import parse_relative_time_expression
from app.ui.task_controller import TaskController
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


class NewTaskDialog(QDialog):
    """Modal dialog for configuring and scheduling a new persistent task."""

    def __init__(self, task_controller: TaskController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task_controller = task_controller
        self.setWindowTitle("Schedule New Task")
        self.setFixedWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel("Create Scheduled Task / Reminder")
        header.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g. Study AFL reminder")
        form.addRow("Title:", self.title_input)

        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "One-Time Reminder",
            "Interval (Every N minutes)",
            "Daily Schedule",
            "Weekly Schedule",
        ])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Schedule Type:", self.type_combo)

        # Dynamic Schedule Options
        self.time_expr_input = QLineEdit()
        self.time_expr_input.setPlaceholderText("e.g. in 10 minutes, tomorrow at 19:00")
        form.addRow("When / Relative:", self.time_expr_input)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 10080)
        self.interval_spin.setValue(60)
        self.interval_spin.setSuffix(" minutes")
        self.interval_spin.setVisible(False)
        form.addRow("Interval:", self.interval_spin)

        self.daily_time_input = QLineEdit("08:00")
        self.daily_time_input.setPlaceholderText("HH:MM (24h UTC)")
        self.daily_time_input.setVisible(False)
        form.addRow("Daily Time (UTC):", self.daily_time_input)

        self.weekly_day_combo = QComboBox()
        self.weekly_day_combo.addItems(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        self.weekly_day_combo.setVisible(False)
        form.addRow("Weekday:", self.weekly_day_combo)

        self.weekly_time_input = QLineEdit("18:00")
        self.weekly_time_input.setPlaceholderText("HH:MM (24h UTC)")
        self.weekly_time_input.setVisible(False)
        form.addRow("Weekly Time (UTC):", self.weekly_time_input)

        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Prompt or reminder content to execute...")
        self.prompt_input.setFixedHeight(70)
        form.addRow("Prompt / Content:", self.prompt_input)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.create_btn = QPushButton("Schedule Task")
        self.create_btn.setObjectName("primaryButton")
        self.create_btn.clicked.connect(self._create_task)
        btn_layout.addWidget(self.create_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _on_type_changed(self, index: int) -> None:
        is_one_time = (index == 0)
        is_interval = (index == 1)
        is_daily = (index == 2)
        is_weekly = (index == 3)

        self.time_expr_input.setVisible(is_one_time)
        self.interval_spin.setVisible(is_interval)
        self.daily_time_input.setVisible(is_daily)
        self.weekly_day_combo.setVisible(is_weekly)
        self.weekly_time_input.setVisible(is_weekly)

    def _create_task(self) -> None:
        title = self.title_input.text().strip()
        prompt = self.prompt_input.toPlainText().strip()
        if not title:
            QMessageBox.warning(self, "Validation Error", "Please provide a task title.")
            return
        if not prompt:
            prompt = title

        type_idx = self.type_combo.currentIndex()

        try:
            if type_idx == 0:  # One-Time
                time_expr = self.time_expr_input.text().strip() or "in 5 minutes"
                self.task_controller.task_manager.create_reminder(
                    title=title,
                    prompt=prompt,
                    relative_or_exact_time=time_expr,
                )
            elif type_idx == 1:  # Interval
                mins = self.interval_spin.value()
                schedule = TaskSchedule(interval_seconds=mins * 60)
                self.task_controller.create_task(
                    title=title,
                    task_type=TaskType.INTERVAL,
                    schedule=schedule,
                    prompt=prompt,
                )
            elif type_idx == 2:  # Daily
                d_time = self.daily_time_input.text().strip()
                schedule = TaskSchedule(daily_time_utc=d_time)
                self.task_controller.create_task(
                    title=title,
                    task_type=TaskType.DAILY,
                    schedule=schedule,
                    prompt=prompt,
                )
            elif type_idx == 3:  # Weekly
                w_day = self.weekly_day_combo.currentIndex()
                w_time = self.weekly_time_input.text().strip()
                schedule = TaskSchedule(weekly_day=w_day, weekly_time_utc=w_time)
                self.task_controller.create_task(
                    title=title,
                    task_type=TaskType.WEEKLY,
                    schedule=schedule,
                    prompt=prompt,
                )

            self.accept()
        except TaskError as err:
            QMessageBox.warning(self, "Scheduling Error", str(err))
        except Exception as err:
            QMessageBox.warning(self, "Error", f"Failed to schedule task: {err}")


class TasksDialog(QDialog):
    """Management dialog for inspecting, creating, pausing, and deleting scheduled tasks."""

    def __init__(self, task_controller: TaskController, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task_controller = task_controller
        self.setWindowTitle("Scheduled Tasks & Reminders")
        self.resize(720, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Header
        top_layout = QHBoxLayout()
        header_label = QLabel("Scheduled Tasks & Automation")
        header_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        top_layout.addWidget(header_label)
        top_layout.addStretch()

        self.new_task_btn = QPushButton("+ New Task")
        self.new_task_btn.setObjectName("primaryButton")
        self.new_task_btn.clicked.connect(self._open_new_task_dialog)
        top_layout.addWidget(self.new_task_btn)
        layout.addLayout(top_layout)

        # Tabs: Active, Paused, All
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._refresh_current_tab)

        self.active_table = self._create_task_table()
        self.paused_table = self._create_task_table()
        self.all_table = self._create_task_table()

        self.tabs.addTab(self.active_table, "Active")
        self.tabs.addTab(self.paused_table, "Paused")
        self.tabs.addTab(self.all_table, "All Tasks")
        layout.addWidget(self.tabs)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._pause_selected)
        btn_layout.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("Resume")
        self.resume_btn.clicked.connect(self._resume_selected)
        btn_layout.addWidget(self.resume_btn)

        self.run_now_btn = QPushButton("Run Now")
        self.run_now_btn.clicked.connect(self._run_selected_now)
        btn_layout.addWidget(self.run_now_btn)

        self.cancel_btn = QPushButton("Cancel Task")
        self.cancel_btn.clicked.connect(self._cancel_selected)
        btn_layout.addWidget(self.cancel_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setStyleSheet(f"color: {COLOR_DANGER};")
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()

        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.clicked.connect(self._refresh_current_tab)
        btn_layout.addWidget(self.refresh_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        # Populate tables
        self._refresh_all_tables()

    def _create_task_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Title", "Type", "Status", "Next Run (UTC)", "Runs"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        return table

    def _get_current_table(self) -> QTableWidget:
        return self.tabs.currentWidget()

    def _get_selected_task_id(self) -> Optional[str]:
        table = self._get_current_table()
        row = table.currentRow()
        if row >= 0:
            item = table.item(row, 0)
            if item:
                return item.data(Qt.UserRole)
        return None

    def _populate_table(self, table: QTableWidget, tasks: list[Task]) -> None:
        table.setRowCount(len(tasks))
        for row, t in enumerate(tasks):
            title_item = QTableWidgetItem(t.title)
            title_item.setData(Qt.UserRole, t.id)
            type_item = QTableWidgetItem(t.task_type.value.capitalize())

            status_item = QTableWidgetItem(t.status.value.upper())
            if t.status == TaskStatus.ACTIVE:
                status_item.setForeground(Qt.green)
            elif t.status == TaskStatus.PAUSED:
                status_item.setForeground(Qt.yellow)
            elif t.status == TaskStatus.COMPLETED:
                status_item.setForeground(Qt.cyan)
            else:
                status_item.setForeground(Qt.gray)

            next_run_str = t.next_run_at.strftime("%Y-%m-%d %H:%M") if t.next_run_at else "-"
            next_item = QTableWidgetItem(next_run_str)
            runs_item = QTableWidgetItem(f"{t.run_count} ({t.failure_count} err)")

            table.setItem(row, 0, title_item)
            table.setItem(row, 1, type_item)
            table.setItem(row, 2, status_item)
            table.setItem(row, 3, next_item)
            table.setItem(row, 4, runs_item)

    def _refresh_all_tables(self) -> None:
        all_tasks = self.task_controller.list_tasks()
        active = [t for t in all_tasks if t.status == TaskStatus.ACTIVE]
        paused = [t for t in all_tasks if t.status == TaskStatus.PAUSED]

        self._populate_table(self.active_table, active)
        self._populate_table(self.paused_table, paused)
        self._populate_table(self.all_table, all_tasks)

    def _refresh_current_tab(self) -> None:
        self._refresh_all_tables()

    def _open_new_task_dialog(self) -> None:
        dlg = NewTaskDialog(task_controller=self.task_controller, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._refresh_all_tables()

    def _pause_selected(self) -> None:
        tid = self._get_selected_task_id()
        if not tid:
            return
        try:
            self.task_controller.pause_task(tid)
            self._refresh_all_tables()
        except TaskError as err:
            QMessageBox.warning(self, "Notice", str(err))

    def _resume_selected(self) -> None:
        tid = self._get_selected_task_id()
        if not tid:
            return
        try:
            self.task_controller.resume_task(tid)
            self._refresh_all_tables()
        except TaskError as err:
            QMessageBox.warning(self, "Notice", str(err))

    def _cancel_selected(self) -> None:
        tid = self._get_selected_task_id()
        if not tid:
            return
        try:
            self.task_controller.cancel_task(tid)
            self._refresh_all_tables()
        except TaskError as err:
            QMessageBox.warning(self, "Notice", str(err))

    def _delete_selected(self) -> None:
        tid = self._get_selected_task_id()
        if not tid:
            return
        ans = QMessageBox.question(self, "Confirm Delete", "Permanently delete this task and its history?")
        if ans == QMessageBox.Yes:
            self.task_controller.delete_task(tid)
            self._refresh_all_tables()

    def _run_selected_now(self) -> None:
        tid = self._get_selected_task_id()
        if not tid:
            return
        try:
            exec_rec = self.task_controller.run_task_now(tid)
            msg = f"Task execution finished ({exec_rec.status}):\n{exec_rec.result_summary or exec_rec.error_summary or 'No output'}"
            QMessageBox.information(self, "Task Execution", msg)
            self._refresh_all_tables()
        except TaskError as err:
            QMessageBox.warning(self, "Notice", str(err))
