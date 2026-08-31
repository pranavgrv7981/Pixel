"""SQLite schema management and database connection for triggers and event history."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger

logger = get_logger("events.database")


class EventDatabase:
    """Manages SQLite tables for triggers and bounded event audit history."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db_path = db_path or self.settings.get_resolved_database_path()
        self._ensure_parent_dir()
        self.initialize_schema()

    def _ensure_parent_dir(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Open a SQLite connection."""
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
            logger.error("Failed to connect to event database at '%s': %s", self.db_path, err)
            raise StorageError(f"Event database connection error: {err}") from err

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic SQLite transaction."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as err:
            conn.rollback()
            logger.error("Event database transaction rollback: %s", err)
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        """Idempotently initialize triggers and event_history tables."""
        logger.info("Initializing event automation schema at '%s'...", self.db_path)
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS triggers (
                    trigger_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    event_type TEXT NOT NULL,
                    conditions_json TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    cooldown_seconds INTEGER NOT NULL DEFAULT 300,
                    last_triggered_at TEXT,
                    trigger_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_triggers_status_event ON triggers(status, event_type);

                CREATE TABLE IF NOT EXISTS event_history (
                    record_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    matched_triggers_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_event_history_timestamp ON event_history(timestamp DESC);
            """)
        logger.info("Event automation schema initialized successfully.")
