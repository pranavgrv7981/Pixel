"""Local agent quality telemetry tracking and metrics database."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Optional

from app.agent.intelligence_models import AgentTelemetryRecord
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("agent.telemetry")


class AgentQualityTracker:
    """Records interaction-level quality metrics in assistant.db and computes summary statistics."""

    def __init__(self, db_path: Optional[Path] = None, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = db_path or self.settings.get_resolved_database_path()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        """Create the telemetry table if not already existing."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_quality_telemetry (
                    interaction_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    intent_category TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    tool_count INTEGER NOT NULL DEFAULT 0,
                    retries_count INTEGER NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL DEFAULT 1,
                    goal_achieved INTEGER NOT NULL DEFAULT 1,
                    latency_seconds REAL NOT NULL DEFAULT 0.0,
                    false_completion_prevented INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()

    def record(self, record: AgentTelemetryRecord) -> None:
        """Persist a single interaction quality telemetry event."""
        if not getattr(self.settings, "quality_telemetry_enabled", True):
            return

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_quality_telemetry (
                        interaction_id, timestamp, intent_category, action_type, model_name,
                        tool_count, retries_count, success, goal_achieved, latency_seconds,
                        false_completion_prevented
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.interaction_id,
                        record.timestamp.isoformat(),
                        record.intent_category,
                        record.action_type,
                        record.model_name,
                        record.tool_count,
                        record.retries_count,
                        1 if record.success else 0,
                        1 if record.goal_achieved else 0,
                        record.latency_seconds,
                        1 if record.false_completion_prevented else 0,
                    ),
                )
                conn.commit()
        except Exception as err:
            logger.warning("Failed to record quality telemetry: %s", err)

    def get_metrics_summary(self) -> dict[str, Any]:
        """Compute aggregated quality statistics across recorded interactions."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_interactions,
                        SUM(success) as successful_interactions,
                        SUM(goal_achieved) as goals_achieved,
                        SUM(tool_count) as total_tools,
                        SUM(retries_count) as total_retries,
                        AVG(latency_seconds) as avg_latency,
                        SUM(false_completion_prevented) as total_false_completions_prevented
                    FROM agent_quality_telemetry
                """)
                row = cursor.fetchone()
                if not row or not row["total_interactions"]:
                    return {
                        "total_interactions": 0,
                        "goal_completion_rate": 1.0,
                        "success_rate": 1.0,
                        "avg_retries": 0.0,
                        "avg_latency": 0.0,
                        "false_completions_prevented": 0,
                    }

                total = row["total_interactions"]
                return {
                    "total_interactions": total,
                    "goal_completion_rate": round(row["goals_achieved"] / total, 3) if total else 1.0,
                    "success_rate": round(row["successful_interactions"] / total, 3) if total else 1.0,
                    "avg_retries": round(row["total_retries"] / total, 2) if total else 0.0,
                    "avg_latency": round(row["avg_latency"] or 0.0, 2),
                    "false_completions_prevented": row["total_false_completions_prevented"],
                }
        except Exception as err:
            logger.warning("Failed to compute telemetry summary: %s", err)
            return {"total_interactions": 0, "error": str(err)}
