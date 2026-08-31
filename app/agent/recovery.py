"""Failure classification, repetition detection, and intelligent recovery management."""

import hashlib
import json
from typing import Any, Optional
from app.agent.intelligence_models import FailureAssessment, FailureCategory
from app.core.logging import get_logger

logger = get_logger("agent.recovery")


class FailureRecoveryManager:
    """Classifies execution failures, detects duplicate loops, and guides safe recovery."""

    def __init__(self, max_retries: int = 2, max_repetitions: int = 2) -> None:
        self.max_retries = max_retries
        self.max_repetitions = max_repetitions
        self._fingerprints_history: list[str] = []

    def compute_fingerprint(self, tool_name: str, arguments: dict[str, Any], result_str: str) -> str:
        """Generate a deterministic MD5 hash identifying a tool invocation and outcome."""
        serialized = f"{tool_name}|{json.dumps(arguments, sort_keys=True)}|{result_str.strip()}"
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()

    def record_and_check_repetition(self, tool_name: str, arguments: dict[str, Any], result_str: str) -> bool:
        """Record execution fingerprint and return True if duplicate execution threshold is exceeded."""
        fp = self.compute_fingerprint(tool_name, arguments, result_str)
        self._fingerprints_history.append(fp)
        count = self._fingerprints_history.count(fp)
        if count >= self.max_repetitions:
            logger.warning("Repetition detected for tool '%s' (fingerprint %s repeated %d times)", tool_name, fp[:8], count)
            return True
        return False

    def clear_history(self) -> None:
        """Reset fingerprint history between user turns."""
        self._fingerprints_history.clear()

    def assess_failure(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        error_msg: str,
        current_retries: int = 0,
    ) -> FailureAssessment:
        """Classify tool failure and decide whether automated retry or alternative is safe."""
        norm_err = (error_msg or "").lower()

        # 1. Security / Permission Denials -> NEVER RETRY
        if any(w in norm_err for w in ["denied by safety policy", "security rejection", "forbidden", "permission denied", "path guard", "outside allowed"]):
            category = FailureCategory.SECURITY if "safety policy" in norm_err or "rejection" in norm_err else FailureCategory.PERMISSION_DENIED
            return FailureAssessment(
                category=category,
                is_retryable=False,
                safe_alternative=None,
                explanation="Operation was blocked by safety policy or filesystem permissions. Cannot retry automatically.",
            )

        # 2. Target Not Found
        if any(w in norm_err for w in ["not found", "no such file", "does not exist", "missing"]):
            return FailureAssessment(
                category=FailureCategory.NOT_FOUND,
                is_retryable=False,
                safe_alternative="search_files",
                explanation=f"Target resource was not found. Please verify the filename or path.",
            )

        # 3. Invalid Arguments
        if any(w in norm_err for w in ["validation failed", "missing required", "invalid argument", "type error"]):
            return FailureAssessment(
                category=FailureCategory.INVALID_INPUT,
                is_retryable=False,
                safe_alternative=None,
                explanation="Tool arguments were invalid or missing required parameters.",
            )

        # 4. Timeouts & Transient Errors
        if any(w in norm_err for w in ["timeout", "timed out", "temporary", "busy", "locked"]):
            is_retry = current_retries < self.max_retries
            return FailureAssessment(
                category=FailureCategory.TIMEOUT if "timeout" in norm_err else FailureCategory.TRANSIENT,
                is_retryable=is_retry,
                safe_alternative=None,
                explanation=f"Operation timed out or encountered a temporary resource lock (retry {current_retries + 1}/{self.max_retries}).",
            )

        # 5. Logical / Compilation / Execution Errors
        if any(w in norm_err for w in ["division by zero", "syntax error", "compilation failed", "segfault", "exit code"]):
            return FailureAssessment(
                category=FailureCategory.LOGICAL,
                is_retryable=False,
                safe_alternative=None,
                explanation="The operation produced a logical, mathematical, or compilation failure.",
            )

        # 6. Default Environmental Failure
        is_retry = current_retries < self.max_retries
        return FailureAssessment(
            category=FailureCategory.ENVIRONMENT,
            is_retryable=is_retry,
            safe_alternative=None,
            explanation=f"Operation encountered an unexpected error: {error_msg}",
        )
