"""Tests for browser URL validation, scheme restrictions, and network boundary enforcement."""

import pytest

from app.core.exceptions import ToolValidationError
from app.browser.security import URLValidator


def test_valid_http_and_https_urls() -> None:
    validator = URLValidator(allow_local_network=False)
    assert validator.validate_url("https://example.com") == "https://example.com"
    assert validator.validate_url("http://python.org/doc") == "http://python.org/doc"
    assert validator.validate_url("https://github.com/ollama/ollama?tab=readme") == "https://github.com/ollama/ollama?tab=readme"


def test_url_normalization() -> None:
    validator = URLValidator(allow_local_network=False)
    # Automatically prepends https:// to domain-like strings
    assert validator.validate_url("example.com") == "https://example.com"
    assert validator.validate_url("   github.com/search   ") == "https://github.com/search"


def test_forbidden_schemes_rejected() -> None:
    validator = URLValidator(allow_local_network=False)
    forbidden = [
        "file:///etc/passwd",
        "file://C:/Windows/System32",
        "javascript:alert(1)",
        "javascript:void(0)",
        "data:text/html,<h1>Hacked</h1>",
        "vbscript:msgbox(1)",
        "about:blank",
        "chrome://settings",
    ]
    for bad in forbidden:
        with pytest.raises(ToolValidationError) as exc_info:
            validator.validate_url(bad)
        assert "strictly prohibited" in str(exc_info.value).lower() or "not permitted" in str(exc_info.value).lower()


def test_empty_and_malformed_urls_rejected() -> None:
    validator = URLValidator(allow_local_network=False)
    for bad in ("", "   ", None, "http://", "not_a_valid_url_without_tld"):
        with pytest.raises(ToolValidationError):
            validator.validate_url(bad)


def test_local_and_private_network_blocking() -> None:
    validator = URLValidator(allow_local_network=False)
    local_targets = [
        "http://localhost",
        "http://localhost:8080/admin",
        "http://127.0.0.1",
        "http://127.0.0.1:11434",
        "http://192.168.1.1/router",
        "http://10.0.0.1/internal",
        "http://172.16.0.1/dashboard",
        "http://myrouter.local",
    ]
    for target in local_targets:
        with pytest.raises(ToolValidationError) as exc_info:
            validator.validate_url(target)
        assert "prohibited by security policy" in str(exc_info.value).lower()


def test_local_network_allowed_when_configured() -> None:
    validator = URLValidator(allow_local_network=True)
    assert validator.validate_url("http://localhost:8000") == "http://localhost:8000"
    assert validator.validate_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert validator.validate_url("http://192.168.1.100") == "http://192.168.1.100"
