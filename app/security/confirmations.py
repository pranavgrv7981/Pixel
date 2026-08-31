"""User confirmation interfaces and providers for approval-gated tool actions."""

from abc import ABC, abstractmethod
import json
import sys
from typing import Optional

from app.core.logging import get_logger
from app.security.permissions import ExecutionContext, SecurityDecision

logger = get_logger("security.confirmation")


class ConfirmationProvider(ABC):
    """Abstract interface for prompting the user for approval."""

    @abstractmethod
    def request_confirmation(self, context: ExecutionContext, decision: SecurityDecision) -> bool:
        """Prompt user for confirmation. Returns True if approved, False otherwise."""
        pass


class CliConfirmationProvider(ConfirmationProvider):
    """Terminal/CLI interactive confirmation provider."""

    def request_confirmation(self, context: ExecutionContext, decision: SecurityDecision) -> bool:
        """Display an interactive terminal confirmation prompt and read response."""
        args_display = json.dumps(context.arguments, indent=2, default=str) if context.arguments else "(none)"
        prompt_text = f"""
======================================================================
  [SECURITY CONFIRMATION REQUIRED]
======================================================================
  Tool:       {context.tool_name}
  Risk Level: {context.risk_level.value}
  Reason:     {decision.reason}
  Request ID: {context.request_id}
  Arguments:
{args_display}
======================================================================
Allow this action? [y/N]: """

        try:
            raw_ans = input(prompt_text).strip().lower()
            if raw_ans in ("y", "yes"):
                logger.info("User explicitly approved action '%s' (request_id=%s)", context.tool_name, context.request_id)
                return True

            logger.info(
                "User denied or declined action '%s' (input='%s', request_id=%s)",
                context.tool_name,
                raw_ans,
                context.request_id,
            )
            return False

        except (KeyboardInterrupt, EOFError):
            logger.info("Confirmation prompt cancelled by user interruption (request_id=%s)", context.request_id)
            return False
        except Exception as err:
            logger.error("Unexpected error in CLI confirmation: %s; failing closed", err)
            return False


class NonInteractiveConfirmationProvider(ConfirmationProvider):
    """Provider for automated or non-interactive environments; always denies confirmation."""

    def request_confirmation(self, context: ExecutionContext, decision: SecurityDecision) -> bool:
        logger.warning(
            "Confirmation requested in non-interactive environment for '%s' (request_id=%s); failing closed",
            context.tool_name,
            context.request_id,
        )
        return False


class ConfirmationManager:
    """Manages dispatching confirmation requests to an active confirmation provider."""

    def __init__(self, provider: Optional[ConfirmationProvider] = None) -> None:
        self.provider: Optional[ConfirmationProvider] = provider

    def request_confirmation(self, context: ExecutionContext, decision: SecurityDecision) -> bool:
        """Evaluate confirmation request through provider, failing closed on any issue."""
        if self.provider is None:
            logger.warning(
                "Confirmation requested for '%s' (request_id=%s) but no ConfirmationProvider is registered; failing closed",
                context.tool_name,
                context.request_id,
            )
            return False

        try:
            return bool(self.provider.request_confirmation(context, decision))
        except Exception as err:
            logger.error(
                "ConfirmationProvider raised exception for '%s' (request_id=%s): %s; failing closed",
                context.tool_name,
                context.request_id,
                err,
            )
            return False
