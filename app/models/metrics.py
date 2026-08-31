"""Metrics and performance tracking for model routing decisions and latency."""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.models.profiles import ModelRole
from app.models.selector import RequestCategory


class ModelUsageRecord(BaseModel):
    """Anonymized record of a model inference turn."""

    model_name: str
    role: ModelRole
    category: RequestCategory
    latency_seconds: float
    tool_calls_count: int = 0
    success: bool = True
    is_fallback: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelMetricsTracker:
    """Tracks performance and utilization metrics for local models without storing prompt content."""

    def __init__(self, max_history: int = 200) -> None:
        self.max_history = max_history
        self._history: list[ModelUsageRecord] = []

    def record_usage(
        self,
        model_name: str,
        role: ModelRole,
        category: RequestCategory,
        latency_seconds: float,
        tool_calls_count: int = 0,
        success: bool = True,
        is_fallback: bool = False,
    ) -> None:
        """Record an inference turn."""
        record = ModelUsageRecord(
            model_name=model_name,
            role=role,
            category=category,
            latency_seconds=round(latency_seconds, 3),
            tool_calls_count=tool_calls_count,
            success=success,
            is_fallback=is_fallback,
        )
        self._history.append(record)
        if len(self._history) > self.max_history:
            self._history.pop(0)

    def get_summary(self) -> dict[str, Any]:
        """Aggregate model performance and count summaries."""
        if not self._history:
            return {
                "total_requests": 0,
                "avg_latency_seconds": 0.0,
                "models_used": {},
                "fallbacks_count": 0,
            }

        total = len(self._history)
        avg_latency = sum(r.latency_seconds for r in self._history) / total
        fallbacks = sum(1 for r in self._history if r.is_fallback)

        models_count: dict[str, int] = {}
        for r in self._history:
            models_count[r.model_name] = models_count.get(r.model_name, 0) + 1

        return {
            "total_requests": total,
            "avg_latency_seconds": round(avg_latency, 3),
            "models_used": models_count,
            "fallbacks_count": fallbacks,
        }

    def get_recent_records(self, limit: int = 10) -> list[ModelUsageRecord]:
        """Return the most recent inference usage records."""
        return list(reversed(self._history[-limit:]))
