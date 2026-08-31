"""SQLite database management and schema initialization for scheduled tasks."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger

logger = get_logger("tasks.database")


class TaskDatabase:
    """Manages SQLite connection lifecycle, transactions, and tables for tasks and executions."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db_path = db_path or self.settings.get_resolved_tasks_db_path()
        self._ensure_parent_dir()
        self.initialize_schema()

    def _ensure_parent_dir(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection."""
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            return conn
        except sqlite3.Error as err:
            logger.error("Failed to connect to task database at '%s': %s", self.db_path, err)
            raise StorageError(f"Task database connection error: {err}") from err

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic SQLite transaction."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as err:
            conn.rollback()
            logger.error("Task database transaction rollback due to error: %s", err)
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        """Idempotently create tasks and task_executions tables."""
        logger.info("Initializing task database schema at '%s'...", self.db_path)
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    schedule_json TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_payload_json TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    next_run_at TEXT,
                    last_run_at TEXT,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    max_runs INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status_next_run ON tasks(status, next_run_at);

                CREATE TABLE IF NOT EXISTS task_executions (
                    execution_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    occurrence_id TEXT NOT NULL UNIQUE,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    result_summary TEXT,
                    error_summary TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_task_executions_task_id ON task_executions(task_id);
            """)
        logger.info("Task database schema initialized successfully.")
