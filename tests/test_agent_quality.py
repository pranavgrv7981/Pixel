"""Unit tests for ResponseQualityEvaluator and AgentQualityTracker."""

import pytest
from pathlib import Path
from app.agent.intelligence_models import AgentTelemetryRecord
from app.agent.quality import ResponseQualityEvaluator
from app.agent.telemetry import AgentQualityTracker


def test_false_completion_interception() -> None:
    evaluator = ResponseQualityEvaluator()

    # Tool failed, but model said "Done! I have created the file."
    tool_logs = [{"tool": "create_file", "success": False, "error": "Access is denied"}]
    res = evaluator.evaluate("Done! I have created the file.", tool_executions=tool_logs)

    assert res.false_completion_detected is True
    assert "unable to complete" in res.sanitized_content.lower()
    assert "Access is denied" in res.sanitized_content


def test_clean_json_formatting() -> None:
    evaluator = ResponseQualityEvaluator()
    json_resp = '{"total_ram_gb": 32, "used_ram_gb": 16, "percent": 50.0}'
    res = evaluator.evaluate(json_resp)
    assert not res.sanitized_content.startswith("{")
    assert "**total_ram_gb**: 32" in res.sanitized_content


def test_quality_telemetry(tmp_path: Path) -> None:
    db_path = tmp_path / "test_telemetry.db"
    tracker = AgentQualityTracker(db_path=db_path)
    tracker.initialize()

    # Record two interactions
    tracker.record(
        AgentTelemetryRecord(
            interaction_id="int-1",
            intent_category="simple_chat",
            action_type="answer",
            model_name="qwen3:30b",
            tool_count=0,
            success=True,
            goal_achieved=True,
            latency_seconds=12.5,
        )
    )
    tracker.record(
        AgentTelemetryRecord(
            interaction_id="int-2",
            intent_category="system_query",
            action_type="tool",
            model_name="qwen3:30b",
            tool_count=1,
            success=True,
            goal_achieved=True,
            latency_seconds=18.0,
            false_completion_prevented=True,
        )
    )

    summary = tracker.get_metrics_summary()
    assert summary["total_interactions"] == 2
    assert summary["goal_completion_rate"] == 1.0
    assert summary["false_completions_prevented"] == 1
    assert summary["avg_latency"] > 10.0
