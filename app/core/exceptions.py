"""Domain-specific exceptions for the Local AI Personal Assistant."""

from typing import Any, Optional


class AssistantError(Exception):
    """Base exception for all assistant-related errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message


class ConfigurationError(AssistantError):
    """Raised when application configuration is missing, invalid, or cannot be loaded."""


class ModelError(AssistantError):
    """Raised when model interactions (e.g., Ollama requests, timeouts, connectivity) fail."""


class OllamaConnectionError(ModelError):
    """Raised when the Ollama server is unreachable, connection is refused, or times out."""


class ModelNotFoundError(ModelError):
    """Raised when the specified model is not installed or available on the Ollama server."""


class ModelAPIError(ModelError):
    """Raised when an Ollama API request or stream execution fails."""



class ConversationError(AssistantError):
    """Raised when conversation state, message formatting, or context management encounters an error."""


class InvalidMessageError(ConversationError):
    """Raised when message content or role is invalid (e.g. empty, whitespace, wrong type)."""


class ConversationNotFoundError(ConversationError):
    """Raised when referencing a conversation ID that does not exist."""



class ToolError(AssistantError):
    """Base exception for tool-related failures."""


class ToolNotFoundError(ToolError):
    """Raised when a requested tool does not exist in the registry."""


class ToolValidationError(ToolError):
    """Raised when tool arguments or output validation fails."""


class ToolExecutionError(ToolError):
    """Raised when tool execution encounters an unhandled runtime error."""


class ToolAlreadyExistsError(ToolError):
    """Raised when registering a tool whose name is already registered."""


class ToolRoundLimitError(ToolError):
    """Raised when the maximum number of tool-call iterations/rounds is reached."""


class ToolCallParseError(ToolError):
    """Raised when a model tool-call request is malformed or invalid."""



class SecurityError(AssistantError):
    """Base exception for security, permission, and safety violations."""


class PermissionDeniedError(SecurityError):
    """Raised when an operation or tool execution is denied by user confirmation or policy."""


class ConfirmationRequiredError(SecurityError):
    """Raised when an action requires confirmation but no provider is available to prompt the user."""


class SecurityPolicyError(SecurityError):
    """Raised when a security policy configuration or rule is invalid."""


class SecurityEvaluationError(SecurityError):
    """Raised when an internal error occurs during security evaluation."""



class StorageError(AssistantError):
    """Raised when persistent data storage (SQLite, files, cache) operations fail."""


class VoiceError(AssistantError):
    """Base exception for voice capture, microphone, and speech-to-text failures."""


class MicrophoneUnavailableError(VoiceError):
    """Raised when no valid microphone is detected or access is denied."""


class AudioRecordingError(VoiceError):
    """Raised when audio capture encounters an unexpected hardware or streaming failure."""


class SpeechToTextError(VoiceError):
    """Raised when speech-to-text model loading or transcription fails."""


class TextToSpeechError(VoiceError):
    """Raised when text-to-speech model loading or speech synthesis fails."""


class AudioPlaybackError(VoiceError):
    """Raised when audio output streaming or playback encounters an error."""


class TaskError(AssistantError):
    """Base exception for task management, scheduling, and autonomous execution errors."""


class TaskNotFoundError(TaskError):
    """Raised when a referenced scheduled task cannot be found."""


class TaskValidationError(TaskError):
    """Raised when task parameters, action payloads, or schedule definitions are invalid."""


class TaskExecutionError(TaskError):
    """Raised when an error occurs during scheduled task execution."""


class SchedulerError(TaskError):
    """Raised when the task scheduler encounters a lifecycle or concurrency error."""


class EventError(AssistantError):
    """Base exception for background event engine and watcher operations."""


class TriggerError(EventError):
    """Raised when an error occurs during trigger evaluation or execution."""


class TriggerValidationError(TriggerError):
    """Raised when trigger parameters or conditions fail validation."""


class WatcherError(EventError):
    """Raised when a local watcher (filesystem, system metrics, applications) encounters an error."""




