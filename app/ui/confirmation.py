"""Thread-safe GUI Confirmation Provider integrating with PermissionManager."""

import threading
from typing import Any, Optional
from PySide6.QtCore import QObject, Signal

from app.core.logging import get_logger
from app.security.confirmations import ConfirmationProvider
from app.security.permissions import ExecutionContext, SecurityDecision

logger = get_logger("ui.confirmation")


class GuiConfirmationProvider(QObject):
    """Bridges worker-thread tool permission requests to the Qt main UI thread."""

    # Signal emitted across threads to display confirmation dialog on UI thread
    # Parameters: (ExecutionContext, SecurityDecision, threading.Event, list[bool])
    confirmation_requested = Signal(object, object, object, object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    def request_confirmation(self, context: ExecutionContext, decision: SecurityDecision) -> bool:
        """Request confirmation by dispatching to the Qt main thread and waiting for user decision.

        Fail-closed by default: Returns False if timed out, interrupted, or cancelled.
        """
        logger.info(
            "Worker thread requesting user confirmation for tool '%s' (risk=%s)",
            context.tool_name,
            context.risk_level.value,
        )

        event = threading.Event()
        result_holder: list[bool] = [False]

        # Dispatch request to UI main thread
        self.confirmation_requested.emit(context, decision, event, result_holder)

        # Wait for user interaction on GUI thread (with 2-minute safety timeout)
        finished = event.wait(timeout=120.0)
        if not finished:
            logger.warning("Confirmation request for '%s' timed out; defaulting to DENY", context.tool_name)
            return False

        allowed = bool(result_holder[0])
        logger.info("User confirmation for tool '%s': %s", context.tool_name, "ALLOWED" if allowed else "DENIED")
        return allowed


# Register as a virtual subclass of ConfirmationProvider
ConfirmationProvider.register(GuiConfirmationProvider)
