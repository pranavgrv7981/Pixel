"""Unit tests for PlanController signals and PlanDialog rendering."""

from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication

from app.planning.executor import PlanExecutor
from app.planning.models import Plan, PlanStep, StepStatus
from app.planning.planner import Planner
from app.planning.repository import PlanRepository
from app.ui.plan_controller import PlanController
from app.ui.plan_dialog import PlanDialog


@pytest.fixture
def plan_ui_setup(tmp_path) -> tuple[PlanController, Plan]:
    mock_planner = MagicMock(spec=Planner)
    mock_executor = MagicMock(spec=PlanExecutor)
    mock_repo = MagicMock(spec=PlanRepository)

    controller = PlanController(planner=mock_planner, executor=mock_executor, repository=mock_repo)

    step = PlanStep(order=1, description="Step 1", tool_name="get_current_time")
    plan = Plan(goal="UI test plan", steps=[step])
    return controller, plan


def test_plan_dialog_initialization_and_display(plan_ui_setup: tuple[PlanController, Plan]) -> None:
    app = QApplication.instance() or QApplication([])
    controller, plan = plan_ui_setup

    dialog = PlanDialog(plan_controller=controller, initial_plan=plan)
    assert dialog.goal_label.text().find("UI test plan") != -1
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 2).text() == "get_current_time"
