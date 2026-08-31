"""SQLite database connection management and idempotent schema versioning."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Generator, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger

logger = get_logger("memory.database")

CURRENT_SCHEMA_VERSION = 1


class MemoryDatabase:
    """Manages SQLite connection lifecycle, transactions, and schema migrations."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db_path = db_path or self.settings.get_resolved_database_path()
        self._ensure_parent_dir()

    def _ensure_parent_dir(self) -> None:
        """Ensure parent directory of database exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection."""
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
            logger.error("Failed to connect to SQLite database at '%s': %s", self.db_path, err)
            raise StorageError(f"Database connection error: {err}")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic database transaction with rollback on failure."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as err:
            conn.rollback()
            logger.error("Database transaction rolled back due to error: %s", err)
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Idempotently initialize tables, indexes, and schema versioning."""
        logger.info("Initializing memory database at '%s'...", self.db_path)
        with self.transaction() as conn:
            # 1. Schema version table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
            """)

            row = conn.execute("SELECT MAX(version) AS current_ver FROM schema_version;").fetchone()
            current_ver = row["current_ver"] if row and row["current_ver"] is not None else 0

            if current_ver < 1:
                logger.info("Applying schema version 1 migration...")
                # 2. Conversations table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)

                # 3. Messages table with sequence index and cascade delete
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        sequence_number INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_conv_seq
                    ON messages(conversation_id, sequence_number);
                """)

                # 4. Memories table with unique constraint on (category, key) for upsert semantics
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        importance INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(category, key)
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_cat_key
                    ON memories(category, key);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_key
                    ON memories(key);
                """)

                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?);",
                    (1, now),
                )
                logger.info("Schema version 1 applied successfully.")

        logger.info("Memory database initialized successfully.")

    def check_integrity(self) -> bool:
        """Run SQLite integrity check to ensure database file is not corrupted."""
        try:
            with self.transaction() as conn:
                res = conn.execute("PRAGMA integrity_check;").fetchone()
                return res and res[0].lower() == "ok"
        except Exception as err:
            logger.error("Database integrity check failed: %s", err)
            return False
