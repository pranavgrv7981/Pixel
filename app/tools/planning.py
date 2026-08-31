"""Tools for creating, querying, and managing multi-step plans."""

from typing import TYPE_CHECKING, Any, Optional
from pydantic import BaseModel, Field

from app.tools.base import RiskLevel, Tool, ToolResult

if TYPE_CHECKING:
    from app.planning.executor import PlanExecutor
    from app.planning.planner import Planner
    from app.planning.repository import PlanRepository


class CreatePlanArgs(BaseModel):
    goal: str = Field(description="The complex task or objective to create a plan for")


class CreatePlanTool(Tool):
    """Decomposes a complex objective into a structured multi-step plan."""

    def __init__(self, planner: "Planner", repository: "PlanRepository") -> None:
        super().__init__(
            name="create_plan",
            description="Decompose a complex user goal into a structured multi-step plan.",
            risk_level=RiskLevel.READ,
            args_model=CreatePlanArgs,
        )
        self.planner = planner
        self.repository = repository

    def _run(self, args: dict[str, Any]) -> ToolResult:
        goal = args.get("goal")
        if not goal:
            return ToolResult(success=False, error="Parameter 'goal' is required.")

        try:
            plan = self.planner.create_plan(goal=goal)
            self.repository.save_plan(plan)

            steps_desc = "\n".join(
                f"  {s.order}. [{s.tool_name}] {s.description} (Risk: {s.risk_level.value})" for s in plan.steps
            )
            output = (
                f"Plan created successfully:\n"
                f"Plan ID: {plan.id}\n"
                f"Goal: {plan.goal}\n"
                f"Status: {plan.status.value}\n"
                f"Steps ({len(plan.steps)}):\n{steps_desc}\n"
                f"Requires Upfront Approval: {plan.requires_user_approval}"
            )
            return ToolResult(success=True, data=output)
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to create plan: {err}")


class GetPlanStatusArgs(BaseModel):
    plan_id: str = Field(description="Unique identifier of the plan to query")


class GetPlanStatusTool(Tool):
    """Query current execution status, steps, and progress of a plan."""

    def __init__(self, repository: "PlanRepository") -> None:
        super().__init__(
            name="get_plan_status",
            description="Get the status, step progress, and results of a multi-step plan.",
            risk_level=RiskLevel.READ,
            args_model=GetPlanStatusArgs,
        )
        self.repository = repository

    def _run(self, args: dict[str, Any]) -> ToolResult:
        plan_id = args.get("plan_id")
        if not plan_id:
            return ToolResult(success=False, error="Parameter 'plan_id' is required.")

        plan = self.repository.get_plan(plan_id)
        if not plan:
            return ToolResult(success=False, error=f"Plan '{plan_id}' not found.")

        steps_summary = "\n".join(
            f"  Step {s.order} [{s.tool_name}]: {s.description} -> {s.status.value}"
            + (f" ({s.result_summary})" if s.result_summary else "")
            + (f" [Error: {s.error_message}]" if s.error_message else "")
            for s in plan.steps
        )

        output = (
            f"Plan ID: {plan.id}\n"
            f"Goal: {plan.goal}\n"
            f"Status: {plan.status.value}\n"
            f"Version: {plan.version}\n"
            f"Steps Progress:\n{steps_summary}\n"
            f"Final Summary: {plan.final_summary or 'In progress'}"
        )
        return ToolResult(success=True, data=output)


class ListPlansArgs(BaseModel):
    limit: Optional[int] = Field(default=10, description="Maximum number of plans to return (default 10)")


class ListPlansTool(Tool):
    """List recent plans and their statuses."""

    def __init__(self, repository: "PlanRepository") -> None:
        super().__init__(
            name="list_plans",
            description="List recent multi-step plans and their execution statuses.",
            risk_level=RiskLevel.READ,
            args_model=ListPlansArgs,
        )
        self.repository = repository

    def _run(self, args: dict[str, Any]) -> ToolResult:
        limit = int(args.get("limit", 10))
        plans = self.repository.list_plans(limit=limit)
        if not plans:
            return ToolResult(success=True, data="No plans found in database.")

        lines = [f"Found {len(plans)} recent plans:"]
        for p in plans:
            lines.append(f"- [{p.id[:8]}] '{p.goal}' -> {p.status.value} ({len(p.steps)} steps, v{p.version})")

        return ToolResult(success=True, data="\n".join(lines))


class CancelPlanArgs(BaseModel):
    plan_id: str = Field(description="Unique identifier of the plan to cancel")


class CancelPlanTool(Tool):
    """Cancel an active or pending plan."""

    def __init__(self, executor: "PlanExecutor", repository: "PlanRepository") -> None:
        super().__init__(
            name="cancel_plan",
            description="Cancel an active or pending plan.",
            risk_level=RiskLevel.MEDIUM,
            args_model=CancelPlanArgs,
        )
        self.executor = executor
        self.repository = repository

    def _run(self, args: dict[str, Any]) -> ToolResult:
        plan_id = args.get("plan_id")
        if not plan_id:
            return ToolResult(success=False, error="Parameter 'plan_id' is required.")

        plan = self.repository.get_plan(plan_id)
        if not plan:
            return ToolResult(success=False, error=f"Plan '{plan_id}' not found.")

        from app.planning.models import PlanStatus

        self.executor.cancel()
        plan.status = PlanStatus.CANCELLED
        self.repository.save_plan(plan)

        return ToolResult(success=True, data=f"Plan '{plan_id}' was cancelled.")
