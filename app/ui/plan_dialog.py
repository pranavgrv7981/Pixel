"""Modal dialog for reviewing, starting, visualizing, and controlling multi-step plans."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.planning.models import Plan, PlanStep, PlanStatus, StepStatus
from app.ui.plan_controller import PlanController


class PlanDialog(QDialog):
    """Interactive GUI dialog presenting multi-step plan preview and real-time step execution progress."""

    def __init__(
        self,
        plan_controller: PlanController,
        initial_plan: Optional[Plan] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = plan_controller
        self.plan: Optional[Plan] = initial_plan or self.controller._active_plan

        self.setWindowTitle("Autonomous Planning & Execution")
        self.resize(750, 520)
        self._init_ui()
        self._wire_signals()

        if self.plan:
            self._display_plan(self.plan)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header / Goal Area
        self.goal_label = QLabel("<b>Goal:</b> (No active plan)")
        self.goal_label.setWordWrap(True)
        self.goal_label.setStyleSheet("font-size: 14px; padding: 6px;")
        layout.addWidget(self.goal_label)

        self.status_label = QLabel("<b>Status:</b> Draft")
        self.status_label.setStyleSheet("color: #888; padding-left: 6px;")
        layout.addWidget(self.status_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Steps Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "Status", "Tool", "Description", "Result / Output"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("▶ Start Plan")
        self.start_btn.clicked.connect(self._on_start_clicked)
        btn_layout.addWidget(self.start_btn)

        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        btn_layout.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("⏯ Resume")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._on_resume_clicked)
        btn_layout.addWidget(self.resume_btn)

        self.stop_btn = QPushButton("⏹ Stop / Cancel")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self.stop_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _wire_signals(self) -> None:
        self.controller.plan_generated.connect(self._display_plan)
        self.controller.plan_started.connect(self._on_plan_started)
        self.controller.step_started.connect(self._on_step_started)
        self.controller.step_completed.connect(self._on_step_completed)
        self.controller.step_failed.connect(self._on_step_failed)
        self.controller.plan_paused.connect(self._on_plan_paused)
        self.controller.plan_resumed.connect(self._on_plan_resumed)
        self.controller.plan_completed.connect(self._on_plan_completed)
        self.controller.plan_failed.connect(self._on_plan_failed)
        self.controller.plan_cancelled.connect(self._on_plan_cancelled)

    def _display_plan(self, plan: Plan) -> None:
        self.plan = plan
        self.goal_label.setText(f"<b>Goal:</b> {plan.goal}")
        self.status_label.setText(f"<b>Status:</b> {plan.status.value.upper()} (v{plan.version})")

        self.table.setRowCount(len(plan.steps))
        for row, step in enumerate(plan.steps):
            self.table.setItem(row, 0, QTableWidgetItem(str(step.order)))
            self.table.setItem(row, 1, QTableWidgetItem(self._format_status(step.status)))
            self.table.setItem(row, 2, QTableWidgetItem(step.tool_name))
            self.table.setItem(row, 3, QTableWidgetItem(step.description))
            summary = step.result_summary or step.error_message or ""
            self.table.setItem(row, 4, QTableWidgetItem(summary))

        self.start_btn.setEnabled(plan.status in {PlanStatus.READY, PlanStatus.DRAFT})
        self._update_progress()

    def _format_status(self, status: StepStatus) -> str:
        icons = {
            StepStatus.PENDING: "○ Pending",
            StepStatus.READY: "○ Ready",
            StepStatus.RUNNING: "▶ Running",
            StepStatus.WAITING_CONFIRMATION: "⏳ Confirming",
            StepStatus.COMPLETED: "✓ Completed",
            StepStatus.FAILED: "✖ Failed",
            StepStatus.SKIPPED: "⏭ Skipped",
            StepStatus.BLOCKED: "⛔ Blocked",
            StepStatus.CANCELLED: "⏹ Cancelled",
        }
        return icons.get(status, status.value)

    def _update_progress(self) -> None:
        if not self.plan or not self.plan.steps:
            self.progress_bar.setValue(0)
            return

        done = sum(1 for s in self.plan.steps if s.status == StepStatus.COMPLETED)
        pct = int((done / len(self.plan.steps)) * 100)
        self.progress_bar.setValue(pct)

    def _on_start_clicked(self) -> None:
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.controller.start_active_plan()

    def _on_pause_clicked(self) -> None:
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(True)
        self.controller.pause_active_plan()

    def _on_resume_clicked(self) -> None:
        self.resume_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.controller.resume_active_plan()

    def _on_stop_clicked(self) -> None:
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.controller.stop_active_plan()

    def _on_plan_started(self, plan: Plan) -> None:
        self.status_label.setText(f"<b>Status:</b> RUNNING (v{plan.version})")

    def _on_step_started(self, plan: Plan, step: PlanStep) -> None:
        row = step.order - 1
        if 0 <= row < self.table.rowCount():
            self.table.setItem(row, 1, QTableWidgetItem(self._format_status(StepStatus.RUNNING)))

    def _on_step_completed(self, plan: Plan, step: PlanStep) -> None:
        row = step.order - 1
        if 0 <= row < self.table.rowCount():
            self.table.setItem(row, 1, QTableWidgetItem(self._format_status(StepStatus.COMPLETED)))
            self.table.setItem(row, 4, QTableWidgetItem(step.result_summary or "Done"))
        self._update_progress()

    def _on_step_failed(self, plan: Plan, step: PlanStep, error: str) -> None:
        row = step.order - 1
        if 0 <= row < self.table.rowCount():
            self.table.setItem(row, 1, QTableWidgetItem(self._format_status(StepStatus.FAILED)))
            self.table.setItem(row, 4, QTableWidgetItem(f"Error: {error}"))

    def _on_plan_paused(self, plan: Plan) -> None:
        self.status_label.setText(f"<b>Status:</b> PAUSED (v{plan.version})")

    def _on_plan_resumed(self, plan: Plan) -> None:
        self.status_label.setText(f"<b>Status:</b> RUNNING (v{plan.version})")

    def _on_plan_completed(self, plan: Plan) -> None:
        self.status_label.setText(f"<b>Status:</b> COMPLETED ✓ (v{plan.version})")
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self._update_progress()

    def _on_plan_failed(self, plan: Plan, reason: str) -> None:
        self.status_label.setText(f"<b>Status:</b> FAILED ✖ ({reason})")
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

    def _on_plan_cancelled(self, plan: Plan) -> None:
        self.status_label.setText(f"<b>Status:</b> CANCELLED ⏹")
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
