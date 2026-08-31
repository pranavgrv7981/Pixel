"""Planner orchestrator decomposing user goals into validated, multi-step execution plans."""

import json
import re
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.ollama_client import OllamaClient
from app.planning.context import PlanContextBuilder
from app.planning.models import FailureType, Plan, PlanBudget, PlanStatus, PlanStep, StepStatus
from app.planning.recovery import SecurityDenialGuard
from app.planning.validator import PlanValidator
from app.tools.registry import ToolRegistry

logger = get_logger("planning.planner")

PLANNING_SYSTEM_PROMPT = """You are an expert autonomous task planning engine.
Decompose the user's objective into a clean, sequential, and safe multi-step plan.
Each step MUST reference one of the available registered tools and provide valid JSON parameters.

Available Registered Tools:
{tool_schemas}

RULES:
1. Only use tool names from the available registered tools list.
2. Provide concrete, valid JSON parameters for each tool.
3. Steps should be ordered sequentially from prerequisite to final action.
4. Output MUST be strict valid JSON in the following format and nothing else:
{{
  "goal": "<original goal>",
  "success_criteria": ["<criterion 1>", "<criterion 2>"],
  "steps": [
    {{
      "order": 1,
      "description": "<what this step does>",
      "tool_name": "<exact tool name>",
      "parameters": {{ ... }},
      "dependencies": []
    }},
    {{
      "order": 2,
      "description": "<next step>",
      "tool_name": "<exact tool name>",
      "parameters": {{ ... }},
      "dependencies": ["1"]
    }}
  ]
}}
"""


class Planner:
    """Decomposes goals into structured plans and coordinates dynamic re-planning on failures."""

    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        validator: PlanValidator,
        settings: Optional[Settings] = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.validator = validator
        self.settings = settings or get_settings()
        self.context_builder = PlanContextBuilder(settings=self.settings)

    def create_plan(self, goal: str, context: Optional[str] = None) -> Plan:
        """Generate a validated Plan addressing the user's goal."""
        logger.info("Generating plan for goal: '%s'...", goal)

        # 1. Try template generation for known deterministic developer goals
        template_plan = self._generate_template_plan(goal)
        if template_plan:
            is_valid, errors = self.validator.validate_plan(template_plan)
            if is_valid:
                template_plan.status = PlanStatus.READY
                return template_plan
            logger.debug("Template plan failed validation: %s; falling back to LLM.", errors)

        # 2. LLM Structured Plan Generation
        tools_summary = self._format_tools_summary()
        sys_prompt = PLANNING_SYSTEM_PROMPT.format(tool_schemas=tools_summary)

        user_content = f"Goal: {goal}"
        if context:
            user_content += f"\nContext:\n{context}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            resp_obj = self.client.chat(messages)
            raw_response = resp_obj.content if hasattr(resp_obj, "content") else str(resp_obj)
            plan = self._parse_plan_json(goal, raw_response)
        except Exception as err:

            logger.warning("LLM planning generation failed (%s). Creating fallback single-action plan.", err)
            plan = self._create_fallback_plan(goal)

        # 3. Validate
        is_valid, errors = self.validator.validate_plan(plan)
        if not is_valid:
            logger.warning("Generated plan had errors (%s). Sanity fixing plan...", errors)
            plan = self._sanitize_plan(plan)

        plan.status = PlanStatus.READY
        return plan

    def replan(
        self,
        plan: Plan,
        failed_step: PlanStep,
        error_message: str,
    ) -> Optional[Plan]:
        """Perform controlled re-planning when a step fails during execution."""
        # 1. Check if security denial forbids re-planning
        if failed_step.failure_type:
            allowed, reason = SecurityDenialGuard.is_replan_allowed(failed_step.failure_type)
            if not allowed:
                logger.warning("Re-planning forbidden by security policy: %s", reason)
                return None

        # 2. Check budget limit
        if plan.budget.replans_count >= plan.budget.max_replans:
            logger.warning("Cannot replan: maximum replan budget (%d) reached.", plan.budget.max_replans)
            return None

        logger.info("Initiating re-plan for plan '%s' after failure in step %d (%s)...", plan.id, failed_step.order, failed_step.tool_name)
        replan_context = self.context_builder.build_context_for_replan(plan, failed_step, error_message)

        tools_summary = self._format_tools_summary()
        sys_prompt = (
            PLANNING_SYSTEM_PROMPT.format(tool_schemas=tools_summary)
            + "\nCRITICAL: You are repairing an active plan where a previous step failed. Provide the complete updated remaining plan steps."
        )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Please repair and generate an updated execution plan based on the failure context:\n{replan_context}"},
        ]

        try:
            resp_obj = self.client.chat(messages)
            raw_response = resp_obj.content if hasattr(resp_obj, "content") else str(resp_obj)
            repaired_plan = self._parse_plan_json(plan.goal, raw_response)
        except Exception as err:

            logger.warning("LLM re-planning failed: %s", err)
            return None

        # Increment version and preserve budget counters
        repaired_plan.id = plan.id
        repaired_plan.version = plan.version + 1
        repaired_plan.budget = plan.budget
        repaired_plan.budget.replans_count += 1

        is_valid, errors = self.validator.validate_plan(repaired_plan)
        if not is_valid:
            logger.warning("Repaired plan failed validation: %s", errors)
            return None

        repaired_plan.status = PlanStatus.READY
        logger.info("Plan '%s' successfully re-planned to version %d (%d steps).", repaired_plan.id, repaired_plan.version, len(repaired_plan.steps))
        return repaired_plan

    def _format_tools_summary(self) -> str:
        """Build concise schema descriptions of registered tools."""
        lines = []
        for schema in self.registry.get_schemas():
            fn = schema.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            props = fn.get("parameters", {}).get("properties", {}) if isinstance(fn.get("parameters"), dict) else {}
            params = ", ".join(props.keys()) if props else ""
            tool_obj = self.registry.get(name) if self.registry.has(name) else None
            risk = tool_obj.risk_level.value if tool_obj else "READ"
            lines.append(f"- {name}({params}): {desc} [Risk: {risk}]")
        return "\n".join(lines)



    def _parse_plan_json(self, goal: str, text: str) -> Plan:
        """Extract and parse structured JSON plan from model response."""
        # Find JSON block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        raw_json = json_match.group(1) if json_match else text.strip()

        # Extract outer object if prose surrounds it
        start_idx = raw_json.find("{")
        end_idx = raw_json.rfind("}")
        if start_idx != -1 and end_idx != -1:
            raw_json = raw_json[start_idx : end_idx + 1]

        data = json.loads(raw_json)

        steps: list[PlanStep] = []
        raw_steps = data.get("steps", [])

        for idx, s in enumerate(raw_steps, start=1):
            tool_name = s.get("tool_name") or s.get("tool") or "get_current_time"
            tool = self.registry.get(tool_name)
            risk = tool.risk_level if tool else RiskLevel.READ

            steps.append(
                PlanStep(
                    order=s.get("order", idx),
                    description=s.get("description") or f"Execute {tool_name}",
                    tool_name=tool_name,
                    parameters=s.get("parameters", {}),
                    dependencies=[str(d) for d in s.get("dependencies", [])],
                    risk_level=risk,
                )
            )

        budget = PlanBudget(
            max_steps=self.settings.max_plan_steps,
            max_tool_calls=self.settings.max_plan_tool_calls,
            max_runtime_seconds=float(self.settings.max_plan_runtime_seconds),
            max_failures=self.settings.max_plan_failures,
            max_replans=self.settings.max_replans,
        )

        plan = Plan(
            goal=data.get("goal") or goal,
            steps=steps,
            budget=budget,
            success_criteria=data.get("success_criteria", []),
        )
        plan.update_safety_assessment()
        return plan

    def _generate_template_plan(self, goal: str) -> Optional[Plan]:
        """Generate deterministic structured plan for standard development workflows."""
        lower = goal.lower()

        # 1. Project preparation / C compile & test template
        if ("prepare" in lower or "build" in lower or "test" in lower) and ("c project" in lower or "project" in lower):
            steps = [
                PlanStep(
                    order=1,
                    description="Inspect project files and directories",
                    tool_name="list_directory",
                    parameters={"directory_path": str(self.settings.data_dir)},
                    dependencies=[],
                ),
                PlanStep(
                    order=2,
                    description="Check git status for uncommitted changes",
                    tool_name="git_status",
                    parameters={},
                    dependencies=["1"],
                ),
                PlanStep(
                    order=3,
                    description="Check system resource usage",
                    tool_name="get_system_info",
                    parameters={},
                    dependencies=["2"],
                ),
            ]
            return Plan(
                goal=goal,
                steps=steps,
                success_criteria=["Project files listed", "Git status clean", "System resources verified"],
            )

        # 2. System and app diagnostic template
        if "system" in lower and ("check" in lower or "status" in lower or "diagnostic" in lower):
            steps = [
                PlanStep(
                    order=1,
                    description="Get system hardware and OS information",
                    tool_name="get_system_info",
                    parameters={},
                ),
                PlanStep(
                    order=2,
                    description="Get CPU usage",
                    tool_name="get_cpu_usage",
                    parameters={},
                    dependencies=["1"],
                ),
                PlanStep(
                    order=3,
                    description="Get memory usage",
                    tool_name="get_memory_usage",
                    parameters={},
                    dependencies=["1"],
                ),
            ]
            return Plan(
                goal=goal,
                steps=steps,
                success_criteria=["Hardware info retrieved", "CPU & RAM metrics collected"],
            )

        return None

    def _create_fallback_plan(self, goal: str) -> Plan:
        """Create a safe minimal single-step plan when model decomposition is unavailable."""
        steps = [
            PlanStep(
                order=1,
                description=f"Inspect system state regarding: {goal}",
                tool_name="get_system_info",
                parameters={},
            )
        ]
        return Plan(goal=goal, steps=steps, success_criteria=["Executed inspection"])

    def _sanitize_plan(self, plan: Plan) -> Plan:
        """Filter out unknown tools and resolve broken dependencies."""
        valid_steps: list[PlanStep] = []
        valid_orders: set[int] = set()

        for step in plan.steps:
            if self.registry.has(step.tool_name):
                step.dependencies = [d for d in step.dependencies if d in [str(o) for o in valid_orders]]
                valid_steps.append(step)
                valid_orders.add(step.order)


        if not valid_steps:
            return self._create_fallback_plan(plan.goal)

        plan.steps = valid_steps
        plan.update_safety_assessment()
        return plan
