"""Unit tests for ModelMetricsTracker utilization and latency accounting."""

import pytest
from app.models.metrics import ModelMetricsTracker
from app.models.profiles import ModelRole
from app.models.selector import RequestCategory


def test_metrics_tracker_records_usage_and_aggregates() -> None:
    tracker = ModelMetricsTracker(max_history=50)
    tracker.record_usage(
        model_name="qwen3:30b",
        role=ModelRole.HEAVY,
        category=RequestCategory.PLANNING,
        latency_seconds=3.5,
        tool_calls_count=2,
    )
    tracker.record_usage(
        model_name="qwen3:8b",
        role=ModelRole.STANDARD,
        category=RequestCategory.CODE_TASK,
        latency_seconds=1.5,
        tool_calls_count=1,
    )

    summary = tracker.get_summary()
    assert summary["total_requests"] == 2
    assert summary["avg_latency_seconds"] == 2.5
    assert summary["models_used"]["qwen3:30b"] == 1
    assert summary["models_used"]["qwen3:8b"] == 1

    records = tracker.get_recent_records(limit=5)
    assert len(records) == 2
    assert records[0].model_name == "qwen3:8b"
