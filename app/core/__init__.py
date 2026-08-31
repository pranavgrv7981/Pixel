"""Core package containing configuration, logging, and common exceptions."""

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AssistantError,
    ConfigurationError,
    ConversationError,
    ConversationNotFoundError,
    InvalidMessageError,
    ModelAPIError,
    ModelError,
    ModelNotFoundError,
    OllamaConnectionError,
    PermissionDeniedError,
    SecurityError,
    SecurityEvaluationError,
    SecurityPolicyError,
    ConfirmationRequiredError,
    StorageError,
    ToolAlreadyExistsError,
    ToolCallParseError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolRoundLimitError,
    ToolValidationError,
)
from app.core.logging import get_logger, setup_logging
from app.core.ollama_client import (
    ChatMessage,
    ModelStatus,
    OllamaClient,
    OllamaStatus,
    ServerStatus,
)

__all__ = [
    "Settings",
    "get_settings",
    "setup_logging",
    "get_logger",
    "AssistantError",
    "ConfigurationError",
    "ModelError",
    "OllamaConnectionError",
    "ModelNotFoundError",
    "ModelAPIError",
    "ConversationError",
    "InvalidMessageError",
    "ConversationNotFoundError",
    "ToolError",
    "ToolNotFoundError",
    "ToolValidationError",
    "ToolExecutionError",
    "ToolAlreadyExistsError",
    "ToolRoundLimitError",
    "ToolCallParseError",
    "SecurityError",
    "PermissionDeniedError",
    "ConfirmationRequiredError",
    "SecurityPolicyError",
    "SecurityEvaluationError",
    "StorageError",
    "OllamaClient",

    "OllamaStatus",
    "ServerStatus",
    "ModelStatus",
    "ChatMessage",
    "OllamaManager",
    "SingleInstanceManager",
    "WindowsStartupManager",
]
from app.core.ollama_manager import OllamaManager
from app.core.single_instance import SingleInstanceManager
from app.core.startup import WindowsStartupManager




