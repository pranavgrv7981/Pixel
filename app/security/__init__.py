"""Security, risk classification, and permission control package."""

from app.security.audit import AuditLogger, scrub_sensitive_dict
from app.security.confirmations import (
    CliConfirmationProvider,
    ConfirmationManager,
    ConfirmationProvider,
    NonInteractiveConfirmationProvider,
)
from app.security.manager import PermissionManager
from app.security.permissions import (
    ExecutionContext,
    PermissionDecision,
    SecurityDecision,
)
from app.security.policies import SecurityPolicy

__all__ = [
    "PermissionDecision",
    "ExecutionContext",
    "SecurityDecision",
    "SecurityPolicy",
    "ConfirmationProvider",
    "CliConfirmationProvider",
    "NonInteractiveConfirmationProvider",
    "ConfirmationManager",
    "AuditLogger",
    "scrub_sensitive_dict",
    "PermissionManager",
]
