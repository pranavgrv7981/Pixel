"""Tests for app/core/logging.py."""

import logging
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger, setup_logging


def test_setup_logging_creates_file(isolated_settings: Settings) -> None:
    """Verify that setup_logging creates the configured log file and writes messages."""
    logger = setup_logging(isolated_settings)
    assert logger.name == "assistant"

    log_message = "Test foundation logging message"
    logger.info(log_message)

    # Flush all handlers
    for handler in logger.handlers:
        handler.flush()

    log_file = isolated_settings.get_log_file_path()
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert log_message in content
    assert "INFO" in content


def test_get_logger_namespacing() -> None:
    """Verify get_logger produces properly namespaced logger names."""
    root_log = get_logger()
    assert root_log.name == "assistant"

    agent_log = get_logger("agent")
    assert agent_log.name == "assistant.agent"

    already_prefixed = get_logger("assistant.tools")
    assert already_prefixed.name == "assistant.tools"


def test_log_level_respected(isolated_settings: Settings) -> None:
    """Verify logger level matches settings."""
    isolated_settings.log_level = "WARNING"
    logger = setup_logging(isolated_settings)

    assert logger.level == logging.WARNING
