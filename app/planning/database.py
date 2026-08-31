"""SQLite database schema and connection manager for persistent planning records."""

from pathlib import Path
import sqlite3
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("planning.database")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    is_safe INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    final_summary TEXT,
    budget_json TEXT,
    success_criteria_json TEXT
);

CREATE TABLE IF NOT EXISTS plan_steps (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    description TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    result_summary TEXT,
    error_message TEXT,
    failure_type TEXT,
    retries_used INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_plan_steps_plan_id ON plan_steps(plan_id);

CREATE TABLE IF NOT EXISTS plan_executions (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    steps_completed INTEGER NOT NULL DEFAULT 0,
    steps_failed INTEGER NOT NULL DEFAULT 0,
    summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_plan_executions_plan_id ON plan_executions(plan_id);
"""


class PlanDatabase:
    """Manages SQLite database connection and table schema for planning subsystem."""

    def __init__(self, db_path: Optional[Path] = None, settings: Optional[Settings] = None) -> None:
        self.settings: Settings = settings or get_settings()
        self.db_path: Path = db_path or self.settings.get_resolved_database_path()
        self.initialize()

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection with foreign keys and row factory."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def initialize(self) -> None:
        """Initialize database schema tables and indexes."""
        logger.info("Initializing planning database schema at '%s'...", self.db_path)
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        logger.info("Planning database schema initialized successfully.")
