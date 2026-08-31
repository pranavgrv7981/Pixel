"""Unit tests for automated credential and secret redaction in logs and audits."""

import pytest
from app.core.logging import redact_sensitive_text
from app.security.audit import scrub_sensitive_dict


def test_redact_passwords_and_tokens() -> None:
    samples = [
        ("password=MySecretPassword123", "password=******"),
        ("api_key: sk-1234567890abcdef1234567890", "api_key: sk-******"),
        ("Authorization: Bearer my_secret_oauth_token_123456789", "Authorization: Bearer ******"),
        ("token=ghp_abcdefghijklmnopqrstuvwxyz123456", "token=ghp_******"),
    ]
    for raw, expected in samples:
        redacted = redact_sensitive_text(raw)
        assert "MySecretPassword123" not in redacted
        assert "my_secret_oauth_token" not in redacted
        assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in redacted


def test_scrub_sensitive_dict_keys_and_values() -> None:
    data = {
        "normal_key": "normal_val",
        "password": "SuperSecretPassword",
        "api_key": "sk-secret1234567890",
        "headers": {
            "Authorization": "Bearer token123456789012345",
        }
    }
    scrubbed = scrub_sensitive_dict(data)
    assert scrubbed["password"] == "******"
    assert scrubbed["api_key"] == "******"
    assert "token123456789012345" not in scrubbed["headers"]["Authorization"]
