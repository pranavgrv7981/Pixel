"""Repository layer for persisting and retrieving multi-step plans and execution records."""

from datetime import datetime, timezone
import json
from typing import Any, Optional

from app.core.logging import get_logger
from app.planning.database import PlanDatabase
from app.planning.models import FailureType, Plan, PlanBudget, PlanStatus, PlanStep, StepStatus
from app.tools.base import RiskLevel

logger = get_logger("planning.repository")


class PlanRepository:
    """Provides persistent CRUD operations for multi-step plans, steps, and execution runs."""

    def __init__(self, db: PlanDatabase) -> None:
        self.db = db

    def save_plan(self, plan: Plan) -> None:
        """Insert or update a plan and all its child steps."""
        plan.updated_at = datetime.now(timezone.utc)

        with self.db.get_connection() as conn:
            # 1. Upsert Plan
            conn.execute(
                """
                INSERT INTO plans (
                    id, goal, status, is_safe, version, created_at, updated_at,
                    completed_at, final_summary, budget_json, success_criteria_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    is_safe=excluded.is_safe,
                    version=excluded.version,
                    updated_at=excluded.updated_at,
                    completed_at=excluded.completed_at,
                    final_summary=excluded.final_summary,
                    budget_json=excluded.budget_json,
                    success_criteria_json=excluded.success_criteria_json
                """,
                (
                    plan.id,
                    plan.goal,
                    plan.status.value,
                    1 if plan.is_safe_plan else 0,
                    plan.version,
                    plan.created_at.isoformat(),
                    plan.updated_at.isoformat(),
                    plan.completed_at.isoformat() if plan.completed_at else None,
                    plan.final_summary,
                    plan.budget.model_dump_json(),
                    json.dumps(plan.success_criteria),
                ),
            )

            # 2. Upsert Steps
            for step in plan.steps:
                conn.execute(
                    """
                    INSERT INTO plan_steps (
                        id, plan_id, step_order, description, tool_name,
                        parameters_json, dependencies_json, risk_level, status,
                        result_summary, error_message, failure_type, retries_used,
                        started_at, completed_at, duration_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        step_order=excluded.step_order,
                        description=excluded.description,
                        tool_name=excluded.tool_name,
                        parameters_json=excluded.parameters_json,
                        dependencies_json=excluded.dependencies_json,
                        risk_level=excluded.risk_level,
                        status=excluded.status,
                        result_summary=excluded.result_summary,
                        error_message=excluded.error_message,
                        failure_type=excluded.failure_type,
                        retries_used=excluded.retries_used,
                        started_at=excluded.started_at,
                        completed_at=excluded.completed_at,
                        duration_seconds=excluded.duration_seconds
                    """,
                    (
                        step.id,
                        plan.id,
                        step.order,
                        step.description,
                        step.tool_name,
                        json.dumps(step.parameters),
                        json.dumps(step.dependencies),
                        step.risk_level.value,
                        step.status.value,
                        step.result_summary,
                        step.error_message,
                        step.failure_type.value if step.failure_type else None,
                        step.retries_used,
                        step.started_at.isoformat() if step.started_at else None,
                        step.completed_at.isoformat() if step.completed_at else None,
                        step.duration_seconds,
                    ),
                )
            conn.commit()

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """Fetch a complete plan including its child steps by ID."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            if not row:
                return None

            step_rows = conn.execute(
                "SELECT * FROM plan_steps WHERE plan_id = ? ORDER BY step_order ASC",
                (plan_id,),
            ).fetchall()

            steps: list[PlanStep] = []
            for sr in step_rows:
                steps.append(
                    PlanStep(
                        id=sr["id"],
                        order=sr["step_order"],
                        description=sr["description"],
                        tool_name=sr["tool_name"],
                        parameters=json.loads(sr["parameters_json"]) if sr["parameters_json"] else {},
                        dependencies=json.loads(sr["dependencies_json"]) if sr["dependencies_json"] else [],
                        risk_level=RiskLevel(sr["risk_level"]),
                        status=StepStatus(sr["status"]),
                        result_summary=sr["result_summary"],
                        error_message=sr["error_message"],
                        failure_type=FailureType(sr["failure_type"]) if sr["failure_type"] else None,
                        retries_used=sr["retries_used"],
                        started_at=datetime.fromisoformat(sr["started_at"]) if sr["started_at"] else None,
                        completed_at=datetime.fromisoformat(sr["completed_at"]) if sr["completed_at"] else None,
                        duration_seconds=sr["duration_seconds"],
                    )
                )

            budget_data = json.loads(row["budget_json"]) if row["budget_json"] else {}
            budget = PlanBudget(**budget_data) if budget_data else PlanBudget()

            plan = Plan(
                id=row["id"],
                goal=row["goal"],
                status=PlanStatus(row["status"]),
                steps=steps,
                budget=budget,
                success_criteria=json.loads(row["success_criteria_json"]) if row["success_criteria_json"] else [],
                is_safe_plan=bool(row["is_safe"]),
                version=row["version"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                final_summary=row["final_summary"],
            )
            plan.update_safety_assessment()
            return plan

    def list_plans(self, limit: int = 50) -> list[Plan]:
        """Return list of recent plans."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM plans ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            plans: list[Plan] = []
            for r in rows:
                p = self.get_plan(r["id"])
                if p:
                    plans.append(p)
            return plans

    def delete_plan(self, plan_id: str) -> bool:
        """Delete plan and its steps."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
            conn.commit()
            return cursor.rowcount > 0
