"""SQLite database persistence layer for conversation summaries, user profiles, and project contexts."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.context.models import (
    ConversationSummaryRecord,
    ProjectContext,
    ResponseStyle,
    UserProfile,
)

logger = get_logger("context.database")


class ContextDatabase:
    """Manages SQLite schema initialization and persistence for context state in assistant.db."""

    def __init__(self, db_path: Optional[Path] = None, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = db_path or self.settings.get_resolved_database_path()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a configured SQLite connection with row factories and foreign keys."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self) -> None:
        """Initialize context management tables idempotently."""
        logger.info("Initializing Context database schema at '%s'...", self.db_path)
        with self._get_connection() as conn:
            # 1. Conversation Summaries table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    messages_summarized_count INTEGER NOT NULL DEFAULT 0,
                    last_message_index INTEGER NOT NULL DEFAULT 0,
                    topics TEXT NOT NULL DEFAULT '[]',
                    decisions TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # 2. User Profile singleton table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    preferred_name TEXT,
                    response_style TEXT NOT NULL DEFAULT 'balanced',
                    preferred_language TEXT NOT NULL DEFAULT 'English',
                    technical_level TEXT NOT NULL DEFAULT 'intermediate',
                    timezone TEXT,
                    custom_instructions TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # 3. Project Contexts table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_contexts (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    root_path TEXT,
                    primary_language TEXT,
                    description TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_project_contexts_active ON project_contexts(is_active)")
            conn.commit()
        logger.info("Context database schema initialized successfully.")

    # -------------------------------------------------------------------------
    # Conversation Summary CRUD
    # -------------------------------------------------------------------------
    def get_summary(self, conversation_id: str) -> Optional[ConversationSummaryRecord]:
        """Fetch stored summary for a conversation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT conversation_id, summary, messages_summarized_count, last_message_index,
                       topics, decisions, created_at, updated_at
                FROM conversation_summaries
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return ConversationSummaryRecord(
                conversation_id=row["conversation_id"],
                summary=row["summary"],
                messages_summarized_count=row["messages_summarized_count"],
                last_message_index=row["last_message_index"],
                topics=json.loads(row["topics"]),
                decisions=json.loads(row["decisions"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def upsert_summary(
        self,
        conversation_id: str,
        summary: str,
        messages_summarized_count: int,
        last_message_index: int,
        topics: Optional[list[str]] = None,
        decisions: Optional[list[str]] = None,
    ) -> ConversationSummaryRecord:
        """Store or update a conversation summary record."""
        now = datetime.now(timezone.utc).isoformat()
        topics_json = json.dumps(topics or [])
        decisions_json = json.dumps(decisions or [])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_summaries (
                    conversation_id, summary, messages_summarized_count, last_message_index,
                    topics, decisions, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    summary = excluded.summary,
                    messages_summarized_count = excluded.messages_summarized_count,
                    last_message_index = excluded.last_message_index,
                    topics = excluded.topics,
                    decisions = excluded.decisions,
                    updated_at = excluded.updated_at
                """,
                (
                    conversation_id,
                    summary,
                    messages_summarized_count,
                    last_message_index,
                    topics_json,
                    decisions_json,
                    now,
                    now,
                ),
            )
            conn.commit()

        return self.get_summary(conversation_id)  # type: ignore

    def delete_summary(self, conversation_id: str) -> bool:
        """Delete summary record for a conversation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (conversation_id,))
            conn.commit()
            return cursor.rowcount > 0

    # -------------------------------------------------------------------------
    # User Profile CRUD
    # -------------------------------------------------------------------------
    def get_user_profile(self) -> UserProfile:
        """Fetch persistent user profile settings (or default if unpopulated)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT preferred_name, response_style, preferred_language, technical_level,
                       timezone, custom_instructions, updated_at
                FROM user_profile
                WHERE id = 1
                """
            )
            row = cursor.fetchone()
            if not row:
                # Return default profile derived from config
                default_style = ResponseStyle.BALANCED
                try:
                    default_style = ResponseStyle(self.settings.default_response_style.lower())
                except Exception:
                    pass
                return UserProfile(
                    preferred_name=None,
                    response_style=default_style,
                    preferred_language="English",
                    technical_level="intermediate",
                    timezone=None,
                    custom_instructions=None,
                )

            try:
                resp_style = ResponseStyle(row["response_style"].lower())
            except ValueError:
                resp_style = ResponseStyle.BALANCED

            return UserProfile(
                preferred_name=row["preferred_name"],
                response_style=resp_style,
                preferred_language=row["preferred_language"],
                technical_level=row["technical_level"],
                timezone=row["timezone"],
                custom_instructions=row["custom_instructions"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def save_user_profile(self, profile: UserProfile) -> UserProfile:
        """Save or update the singleton user profile."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_profile (
                    id, preferred_name, response_style, preferred_language, technical_level,
                    timezone, custom_instructions, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    preferred_name = excluded.preferred_name,
                    response_style = excluded.response_style,
                    preferred_language = excluded.preferred_language,
                    technical_level = excluded.technical_level,
                    timezone = excluded.timezone,
                    custom_instructions = excluded.custom_instructions,
                    updated_at = excluded.updated_at
                """,
                (
                    profile.preferred_name,
                    profile.response_style.value,
                    profile.preferred_language,
                    profile.technical_level,
                    profile.timezone,
                    profile.custom_instructions,
                    now,
                ),
            )
            conn.commit()
        return self.get_user_profile()

    # -------------------------------------------------------------------------
    # Project Context CRUD
    # -------------------------------------------------------------------------
    def get_active_project(self) -> Optional[ProjectContext]:
        """Fetch the currently active project context if any."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, project_name, root_path, primary_language, description, is_active, metadata, updated_at
                FROM project_contexts
                WHERE is_active = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ProjectContext(
                id=row["id"],
                project_name=row["project_name"],
                root_path=row["root_path"],
                primary_language=row["primary_language"],
                description=row["description"],
                is_active=bool(row["is_active"]),
                metadata=json.loads(row["metadata"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def set_active_project(self, project: ProjectContext) -> ProjectContext:
        """Upsert project context and mark it as active (deactivating others)."""
        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(project.metadata or {})

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Deactivate all existing projects if this one is marked active
            if project.is_active:
                cursor.execute("UPDATE project_contexts SET is_active = 0")

            cursor.execute(
                """
                INSERT INTO project_contexts (
                    id, project_name, root_path, primary_language, description, is_active, metadata, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_name = excluded.project_name,
                    root_path = excluded.root_path,
                    primary_language = excluded.primary_language,
                    description = excluded.description,
                    is_active = excluded.is_active,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    project.id,
                    project.project_name,
                    project.root_path,
                    project.primary_language,
                    project.description,
                    1 if project.is_active else 0,
                    metadata_json,
                    now,
                ),
            )
            conn.commit()
        return project

    def list_projects(self) -> list[ProjectContext]:
        """List all stored project contexts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, project_name, root_path, primary_language, description, is_active, metadata, updated_at
                FROM project_contexts
                ORDER BY is_active DESC, updated_at DESC
                """
            )
            rows = cursor.fetchall()
            return [
                ProjectContext(
                    id=row["id"],
                    project_name=row["project_name"],
                    root_path=row["root_path"],
                    primary_language=row["primary_language"],
                    description=row["description"],
                    is_active=bool(row["is_active"]),
                    metadata=json.loads(row["metadata"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]

    def delete_project(self, project_id: str) -> bool:
        """Delete a project context by id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM project_contexts WHERE id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount > 0
