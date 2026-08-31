"""Unit tests for SQLite PlanDatabase and PlanRepository CRUD operations."""

from pathlib import Path
import pytest

from app.planning.database import PlanDatabase
from app.planning.models import Plan, PlanStatus, PlanStep, StepStatus
from app.planning.repository import PlanRepository


@pytest.fixture
def plan_repo(tmp_path: Path) -> PlanRepository:
    db = PlanDatabase(db_path=tmp_path / "test_plans.db")
    return PlanRepository(db=db)


def test_save_and_retrieve_plan(plan_repo: PlanRepository) -> None:
    step = PlanStep(
        order=1,
        description="Inspect files",
        tool_name="list_directory",
        parameters={"directory_path": "data"},
        status=StepStatus.COMPLETED,
        result_summary="Found 3 files",
    )
    plan = Plan(
        goal="Check files in directory",
        status=PlanStatus.COMPLETED,
        steps=[step],
        success_criteria=["Files listed"],
    )

    plan_repo.save_plan(plan)

    retrieved = plan_repo.get_plan(plan.id)
    assert retrieved is not None
    assert retrieved.id == plan.id
    assert retrieved.goal == "Check files in directory"
    assert retrieved.status == PlanStatus.COMPLETED
    assert len(retrieved.steps) == 1
    assert retrieved.steps[0].tool_name == "list_directory"
    assert retrieved.steps[0].result_summary == "Found 3 files"


def test_list_and_delete_plan(plan_repo: PlanRepository) -> None:
    p1 = Plan(goal="Task 1", steps=[PlanStep(order=1, description="D1", tool_name="get_current_time")])
    p2 = Plan(goal="Task 2", steps=[PlanStep(order=1, description="D2", tool_name="get_current_time")])

    plan_repo.save_plan(p1)
    plan_repo.save_plan(p2)

    plans = plan_repo.list_plans(limit=10)
    assert len(plans) == 2

    deleted = plan_repo.delete_plan(p1.id)
    assert deleted is True
    assert plan_repo.get_plan(p1.id) is None
    assert len(plan_repo.list_plans(limit=10)) == 1
