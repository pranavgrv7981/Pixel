"""Context builder for bounded execution history and re-planning prompts."""

from typing import Optional
from app.core.config import Settings, get_settings
from app.planning.models import Plan, PlanStep


class PlanContextBuilder:
    """Builds concise, token-bounded textual execution context for LLM re-planning and observation."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.max_bytes = self.settings.max_plan_context_bytes

    def build_context_for_replan(
        self,
        plan: Plan,
        failed_step: PlanStep,
        error_message: str,
    ) -> str:
        """Format bounded context describing goal, completed steps, and failure reason."""
        lines: list[str] = [
            f"GOAL: {plan.goal}",
            f"PLAN VERSION: {plan.version}",
            f"STATUS: {plan.status.value}",
            f"BUDGET REMAINING: {plan.budget.max_steps - plan.budget.steps_executed} steps, {plan.budget.max_replans - plan.budget.replans_count} replans",
            "",
            "COMPLETED STEPS:",
        ]

        completed = [s for s in plan.steps if s.status.value == "completed"]
        if not completed:
            lines.append("  (No steps completed yet)")
        else:
            for s in completed:
                summary = s.result_summary or "Completed successfully."
                # Truncate summary if too verbose
                if len(summary) > 200:
                    summary = summary[:197] + "..."
                lines.append(f"  Step {s.order} [{s.tool_name}]: {s.description} -> {summary}")

        lines.extend([
            "",
            "FAILED STEP:",
            f"  Step {failed_step.order} [{failed_step.tool_name}]: {failed_step.description}",
            f"  Parameters: {failed_step.parameters}",
            f"  Failure Category: {failed_step.failure_type.value if failed_step.failure_type else 'unknown'}",
            f"  Error Details: {error_message[:400]}",
            "",
            "REMAINING PENDING STEPS:",
        ] )

        pending = [s for s in plan.steps if s.status.value in {"pending", "blocked"}]
        if not pending:
            lines.append("  (No further pending steps)")
        else:
            for s in pending:
                lines.append(f"  Step {s.order} [{s.tool_name}]: {s.description}")

        result_text = "\n".join(lines)
        if len(result_text.encode("utf-8")) > self.max_bytes:
            result_text = result_text[: self.max_bytes - 50] + "\n...[Context truncated to fit budget]"

        return result_text
