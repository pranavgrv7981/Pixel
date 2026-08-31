"""Logging configuration and automated sensitive data redaction for the Local AI Personal Assistant."""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from app.core.config import Settings, get_settings

_LOGGING_INITIALIZED = False

SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(password|secret|token|api_key|apikey|credential|auth)\s*[:=]\s*['\"]?([^'\"\s,;&]+)['\"]?"), r"\1=******"),
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{15,}"), "Bearer ******"),
    (re.compile(r"(?i)ghp_[a-zA-Z0-9]{20,}"), "ghp_******"),
    (re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"), "sk-******"),
]


def redact_sensitive_text(text: str) -> str:
    """Scrub sensitive credentials, tokens, and keys from a string."""
    if not isinstance(text, str) or not text:
        return text
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class RedactingFormatter(logging.Formatter):
    """Custom logging formatter that strips sensitive credentials from all logged messages."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_sensitive_text(original)


def setup_logging(settings: Optional[Settings] = None) -> logging.Logger:
    """Configure application logging handlers and formatters based on settings.

    Args:
        settings: Application settings instance. If None, loaded via get_settings().

    Returns:
        The configured root logger for the application.
    """
    global _LOGGING_INITIALIZED

    if settings is None:
        settings = get_settings()

    settings.ensure_directories()

    log_level = getattr(logging, settings.log_level, logging.INFO)
    root_logger = logging.getLogger("assistant")
    root_logger.setLevel(log_level)

    # Clear existing handlers to allow clean re-initialization during tests
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    formatter = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    if settings.log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File Handler
    if settings.log_to_file:
        log_file_path = settings.get_log_file_path()
        file_handler = RotatingFileHandler(
            filename=str(log_file_path),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Prevent propagating to the global root logger to avoid duplicate lines in console
    root_logger.propagate = False

    _LOGGING_INITIALIZED = True
    root_logger.debug("Logging initialized successfully with active secret redaction (level=%s)", settings.log_level)
    return root_logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retrieve an application logger.

    Args:
        name: Name of the component/module. If provided, namespaced under 'assistant.<name>'.

    Returns:
        logging.Logger instance.
    """
    if not name:
        return logging.getLogger("assistant")
    if name.startswith("assistant"):
        return logging.getLogger(name)
    return logging.getLogger(f"assistant.{name}")
