from typing import Any

from app.core.exceptions import TaskValidationError
from app.tasks.models import TaskActionType



FORBIDDEN_AUTONOMOUS_TOOLS = {
    "delete_file",
    "delete_directory",
    "write_text_file",
    "move_file",
    "rename_file",
    "compile_c_program",
    "run_python_file",
    "run_c_program",
    "run_pytest",
    "close_application",
    "browser_click",
    "browser_type",
}

TASK_CREATION_TOOLS = {
    "create_task",
    "run_task_now",
}


def validate_task_action(action_type: TaskActionType, payload: dict[str, Any]) -> None:
    """Ensure task action is strictly within whitelisted safe categories."""
    if not isinstance(action_type, TaskActionType):
        try:
            action_type = TaskActionType(action_type)
        except ValueError:
            raise TaskValidationError(f"Forbidden or unsupported task action type '{action_type}'")

    if action_type in (
        TaskActionType.ASSISTANT_REMINDER,
        TaskActionType.ASSISTANT_INFORMATION_QUERY,
        TaskActionType.ASSISTANT_MEMORY_QUERY,
        TaskActionType.ASSISTANT_KNOWLEDGE_QUERY,
        TaskActionType.ASSISTANT_MESSAGE,
    ):
        prompt = payload.get("prompt") or payload.get("message")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise TaskValidationError(f"Task action '{action_type.value}' requires a non-empty 'prompt' in payload")


def check_recursive_task_creation(tool_name: str, is_background_context: bool = False) -> bool:
    """Validate whether tool execution is permitted without causing recursive task loops.

    Returns False if background context is attempting recursive task creation, True otherwise.
    """
    if is_background_context and tool_name in TASK_CREATION_TOOLS:
        return False
    return True

