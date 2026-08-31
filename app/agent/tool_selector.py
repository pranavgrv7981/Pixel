"""Capability-aware tool selection and argument pre-validation."""

from typing import Any, Optional
from app.agent.intelligence_models import ActionType, RequestIntent, ToolSelectionDecision
from app.core.logging import get_logger
from app.tools.registry import ToolRegistry

logger = get_logger("agent.tool_selector")

TOOL_CAPABILITY_GROUPS: dict[str, list[str]] = {
    "demo": ["calculate", "get_current_time", "demo_medium_risk_tool"],
    "system": [
        "get_system_info",
        "get_cpu_usage",
        "get_memory_usage",
        "get_battery_status",
        "get_uptime",
        "list_running_processes",
        "get_process_info",
        "open_application",
        "close_application",
        "is_application_running",
    ],
    "filesystem": [
        "list_directory",
        "get_file_info",
        "search_files",
        "read_text_file",
        "create_directory",
        "create_file",
        "write_text_file",
        "copy_file",
        "move_file",
        "rename_file",
        "delete_file",
        "delete_directory",
    ],
    "terminal": [
        "git_status",
        "git_diff",
        "compile_c_program",
        "run_python_file",
        "run_pytest",
        "run_c_program",
    ],
    "memory": ["remember_memory", "recall_memory", "forget_memory"],
    "knowledge": [
        "search_knowledge",
        "list_indexed_documents",
        "index_document",
        "index_directory",
        "remove_document",
    ],
    "browser": [
        "browser_open",
        "browser_search",
        "browser_get_page",
        "browser_current_page",
        "browser_click",
        "browser_type",
        "browser_scroll",
        "browser_back",
        "browser_forward",
        "browser_close",
    ],
    "tasks": [
        "create_task",
        "list_tasks",
        "get_task",
        "pause_task",
        "resume_task",
        "cancel_task",
        "delete_task",
        "run_task_now",
        "get_task_executions",
    ],
    "planning": ["create_plan", "get_plan_status", "list_plans", "cancel_plan"],
}


class CapabilityToolSelector:
    """Selects a minimal, high-confidence subset of tools tailored to the request intent."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry

    def select_tools(
        self,
        intent: RequestIntent,
        all_schemas: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[Optional[list[dict[str, Any]]], ToolSelectionDecision]:
        """Filter registered tool schemas according to intent and return filtered schemas + decision."""
        # 1. Non-tool action paths receive 0 tools
        if intent.action_type in {ActionType.ANSWER, ActionType.CLARIFICATION} or not intent.requires_tools:
            decision = ToolSelectionDecision(
                selected_tools=[],
                confidence=1.0,
                reason=f"Action type is {intent.action_type.value}; tools bypassed to prevent hallucinations.",
                bypassed_tools=[s.get("name", "") for s in (all_schemas or [])],
            )
            return None, decision

        if not all_schemas:
            return None, ToolSelectionDecision(selected_tools=[], reason="No tool schemas available")

        # 2. Gather allowed tool names for suggested groups
        candidate_tool_names: set[str] = set()
        for group in intent.suggested_tool_groups:
            tools_in_group = TOOL_CAPABILITY_GROUPS.get(group, [])
            candidate_tool_names.update(tools_in_group)

        # If specific tool keywords are in prompt, also include those directly
        norm_prompt = intent.raw_prompt.lower()
        if "ram" in norm_prompt or "memory usage" in norm_prompt:
            candidate_tool_names.add("get_memory_usage")
        if "cpu" in norm_prompt:
            candidate_tool_names.add("get_cpu_usage")
        if "time" in norm_prompt or "clock" in norm_prompt:
            candidate_tool_names.add("get_current_time")
        if "calculate" in norm_prompt or any(c.isdigit() for c in norm_prompt):
            candidate_tool_names.add("calculate")
        if "notepad" in norm_prompt or "app" in norm_prompt:
            candidate_tool_names.update(["open_application", "close_application", "is_application_running"])

        # 3. Filter schemas
        selected_schemas: list[dict[str, Any]] = []
        bypassed_tools: list[str] = []

        for schema in all_schemas:
            name = schema.get("name", "")
            if not candidate_tool_names or name in candidate_tool_names:
                selected_schemas.append(schema)
            else:
                bypassed_tools.append(name)

        # Fallback: if filtering left 0 schemas but tools were required, keep all schemas
        if not selected_schemas and all_schemas:
            selected_schemas = all_schemas
            bypassed_tools = []

        selected_names = [s.get("name", "") for s in selected_schemas]
        decision = ToolSelectionDecision(
            selected_tools=selected_names,
            confidence=0.95 if selected_schemas else 0.5,
            reason=f"Selected {len(selected_names)} tools for capability groups {intent.suggested_tool_groups}",
            bypassed_tools=bypassed_tools,
        )

        logger.debug("Tool selector: %d selected, %d bypassed", len(selected_names), len(bypassed_tools))
        return selected_schemas, decision

    def validate_argument_plausibility(self, tool_name: str, args: dict[str, Any]) -> tuple[bool, str]:
        """Pre-execution check ensuring tool arguments are plausible and unambiguous."""
        if not isinstance(args, dict):
            return False, "Arguments must be a key-value dictionary."

        # File operation path checks
        if tool_name in {"read_text_file", "write_text_file", "delete_file", "create_file"}:
            path_val = args.get("path") or args.get("file_path")
            if not path_val or not str(path_val).strip():
                return False, f"Missing required 'path' parameter for tool '{tool_name}'"
            if str(path_val).strip().lower() in {"this", "the file", "report", "it"}:
                return False, f"Ambiguous target path '{path_val}'. Please specify full filename."

        # Application name checks
        if tool_name in {"open_application", "close_application", "is_application_running"}:
            app_val = args.get("app_name") or args.get("application")
            if not app_val or not str(app_val).strip():
                return False, f"Missing required 'app_name' parameter for tool '{tool_name}'"

        # Calculation expression checks
        if tool_name == "calculate":
            expr = args.get("expression")
            if not expr or not str(expr).strip():
                return False, "Calculation expression cannot be empty."

        return True, "Arguments plausible."
