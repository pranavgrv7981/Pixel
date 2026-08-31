"""Plan validation layer enforcing tool existence, acyclic dependencies, and safety boundaries."""

from typing import Optional
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.planning.models import Plan, PlanStep
from app.tools.path_guard import PathGuard
from app.tools.registry import ToolRegistry

logger = get_logger("planning.validator")


class PlanValidationError(Exception):
    """Raised when a plan violates structural, tool, or safety constraints."""

    pass


class PlanValidator:
    """Validates multi-step plans against registered tools, dependency constraints, and security limits."""

    def __init__(
        self,
        registry: ToolRegistry,
        path_guard: Optional[PathGuard] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.registry = registry
        self.path_guard = path_guard
        self.settings = settings or get_settings()

    def validate_plan(self, plan: Plan) -> tuple[bool, list[str]]:
        """Perform comprehensive validation of a plan.

        Returns (is_valid, list_of_error_messages).
        """
        errors: list[str] = []

        # 1. Structural Checks
        if not plan.goal or not plan.goal.strip():
            errors.append("Plan goal cannot be empty.")

        if not plan.steps:
            errors.append("Plan must contain at least one step.")

        if len(plan.steps) > self.settings.max_plan_steps:
            errors.append(
                f"Plan step count ({len(plan.steps)}) exceeds maximum permitted ({self.settings.max_plan_steps})."
            )

        # 2. Step IDs, Orders & Tools Check
        step_ids: set[str] = set()
        step_orders: set[int] = set()

        for step in plan.steps:
            if step.id in step_ids:
                errors.append(f"Duplicate step ID '{step.id}'.")
            step_ids.add(step.id)

            if step.order in step_orders:
                errors.append(f"Duplicate step order '{step.order}'.")
            step_orders.add(step.order)

            # Tool registry check
            if not self.registry.has(step.tool_name):
                errors.append(f"Step {step.order} ('{step.description}') references unknown tool '{step.tool_name}'.")
                continue

            tool = self.registry.get(step.tool_name)


            # Ensure accurate risk level from registered tool (prevent spoofing)
            step.risk_level = tool.risk_level

            # Parameter validation
            try:
                tool.validate_args(step.parameters)
            except Exception as err:
                errors.append(
                    f"Step {step.order} ('{step.tool_name}') has invalid arguments: {err}"
                )

            # Path guard boundary validation if path arguments are present
            if self.path_guard:
                for param_name, param_val in step.parameters.items():
                    if any(k in param_name.lower() for k in ["path", "file", "dir", "directory", "dest", "src"]):
                        if isinstance(param_val, str) and param_val.strip():
                            # Don't validate abstract URLs or commands
                            if not param_val.startswith(("http://", "https://", "about:")):
                                is_valid_path, path_err = self.path_guard.validate_path(param_val)
                                if not is_valid_path:
                                    errors.append(
                                        f"Step {step.order} parameter '{param_name}' violates path boundary: {path_err}"
                                    )

        # 3. Dependency & Cycle Check
        cycle_error = self._check_dependencies_and_cycles(plan.steps)
        if cycle_error:
            errors.append(cycle_error)

        # 4. Update overall safety assessment
        plan.update_safety_assessment()

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Plan '%s' failed validation: %s", plan.id, errors)
        else:
            logger.info("Plan '%s' (%d steps, safe=%s) validated successfully.", plan.id, len(plan.steps), plan.is_safe_plan)

        return is_valid, errors

    def _check_dependencies_and_cycles(self, steps: list[PlanStep]) -> Optional[str]:
        """Verify all step dependencies exist and contain no circular cycles using Kahn's algorithm."""
        id_to_step = {s.id: s for s in steps}
        order_to_id = {str(s.order): s.id for s in steps}

        # Build adjacency graph
        adj: dict[str, list[str]] = {s.id: [] for s in steps}
        in_degree: dict[str, int] = {s.id: 0 for s in steps}

        for s in steps:
            for dep in s.dependencies:
                # Dependency could be an ID or an order number string
                dep_id = dep if dep in id_to_step else order_to_id.get(str(dep))
                if not dep_id:
                    return f"Step {s.order} references non-existent prerequisite dependency '{dep}'."

                if dep_id == s.id:
                    return f"Step {s.order} cannot depend on itself."

                adj[dep_id].append(s.id)
                in_degree[s.id] += 1

        # Kahn's topological sort
        queue = [step_id for step_id, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            node = queue.pop(0)
            visited_count += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(steps):
            return "Plan contains circular or deadlock step dependencies."

        return None
