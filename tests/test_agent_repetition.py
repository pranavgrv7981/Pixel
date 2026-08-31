"""Unit tests for repetition and duplicate loop prevention."""

import pytest
from app.agent.recovery import FailureRecoveryManager
from app.agent.quality import ResponseQualityEvaluator


def test_loop_repetition_detection() -> None:
    mgr = FailureRecoveryManager(max_retries=2, max_repetitions=2)

    # First attempt: not a loop
    is_loop1 = mgr.record_and_check_repetition("read_text_file", {"path": "a.txt"}, "File not found")
    assert is_loop1 is False

    # Second identical attempt: reaches repetition threshold of 2 -> loop detected!
    is_loop2 = mgr.record_and_check_repetition("read_text_file", {"path": "a.txt"}, "File not found")
    assert is_loop2 is True


def test_repetitive_text_deduplication() -> None:
    evaluator = ResponseQualityEvaluator()
    rep_text = "The application is currently running smoothly. The application is currently running smoothly. The application is currently running smoothly."
    result = evaluator.evaluate(rep_text)
    assert len(result.issues) >= 1
    assert "Repetitive sentence detected" in result.issues[0]
    assert result.sanitized_content.count("The application is currently running smoothly") <= 2
