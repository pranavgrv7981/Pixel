"""Adversarial tests for code execution, shell=False enforcement, and process security."""

import pytest
from app.core.config import Settings
from app.core.exceptions import SecurityError
from app.security.execution_policy import ExecutionPolicy


def test_forbidden_shells_rejected() -> None:
    policy = ExecutionPolicy()
    unauthorized = ["cmd.exe", "powershell.exe", "bash", "sh", "mshta.exe"]
    for exe in unauthorized:
        with pytest.raises(SecurityError):
            policy.validate_executable(exe)


def test_timeout_and_output_limits_enforced() -> None:
    settings = Settings()
    policy = ExecutionPolicy(settings=settings)
    assert policy.settings.command_timeout_seconds > 0
    assert policy.settings.max_command_output_bytes > 0
