"""Repository implementations for conversation sessions, messages, and persistent memories."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger
from app.memory.database import MemoryDatabase
from app.memory.models import (
    ConversationRecord,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    MessageRecord,
)

logger = get_logger("memory.repository")


class ConversationRepository:
    """Persistence operations for conversations and messages."""

    def __init__(
        self,
        db: MemoryDatabase,
        settings: Optional[Settings] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def create_conversation(
        self,
        conv_id: Optional[str] = None,
        title: str = "New Conversation",
    ) -> ConversationRecord:
        """Create and store a new conversation record."""
        cid = conv_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at;
                """,
                (cid, title, now, now),
            )
        logger.info("Persisted conversation %s ('%s')", cid, title)
        return ConversationRecord(id=cid, title=title, created_at=now, updated_at=now)

    def get_conversation(self, conv_id: str) -> Optional[ConversationRecord]:
        """Fetch conversation record by UUID."""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?;",
                (conv_id,),
            ).fetchone()
            if not row:
                return None
            return ConversationRecord(
                id=row["id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_conversations(self, limit: int = 50) -> list[ConversationRecord]:
        """List active conversations ordered by last update."""
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
            return [
                ConversationRecord(
                    id=r["id"],
                    title=r["title"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation and all its associated messages."""
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?;", (conv_id,))
            deleted = cur.rowcount > 0
        if deleted:
            logger.info("Deleted conversation %s", conv_id)
        return deleted

    def append_message(
        self,
        conv_id: str,
        role: str,
        content: str,
    ) -> MessageRecord:
        """Append a message to a conversation, pruning oldest messages if max limit is reached."""
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        max_msgs = self.settings.max_persisted_messages

        with self.db.transaction() as conn:
            # Ensure conversation exists
            conv_row = conn.execute("SELECT id FROM conversations WHERE id = ?;", (conv_id,)).fetchone()
            if not conv_row:
                conn.execute(
                    "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                    (conv_id, "New Conversation", now, now),
                )

            # Determine next sequence number
            seq_row = conn.execute(
                "SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_seq FROM messages WHERE conversation_id = ?;",
                (conv_id,),
            ).fetchone()
            seq = seq_row["next_seq"]

            # Insert message
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, sequence_number, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (msg_id, conv_id, role, content, seq, now),
            )

            # Update conversation timestamp
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now, conv_id),
            )

            # Enforce max persisted message retention policy (retain most recent N)
            if max_msgs > 0:
                conn.execute(
                    """
                    DELETE FROM messages
                    WHERE conversation_id = ?
                      AND sequence_number <= (
                          SELECT MAX(sequence_number) - ? FROM messages WHERE conversation_id = ?
                      );
                    """,
                    (conv_id, max_msgs, conv_id),
                )

        return MessageRecord(
            id=msg_id,
            conversation_id=conv_id,
            role=role,
            content=content,
            sequence_number=seq,
            created_at=now,
        )

    def get_messages(
        self,
        conv_id: str,
        limit: Optional[int] = None,
    ) -> list[MessageRecord]:
        """Fetch ordered messages for a conversation."""
        query = "SELECT id, conversation_id, role, content, sequence_number, created_at FROM messages WHERE conversation_id = ? ORDER BY sequence_number ASC"
        params: list[object] = [conv_id]
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self.db.transaction() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                MessageRecord(
                    id=r["id"],
                    conversation_id=r["conversation_id"],
                    role=r["role"],
                    content=r["content"],
                    sequence_number=r["sequence_number"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]


class MemoryRepository:
    """Persistence operations for structured long-term memories."""

    def __init__(self, db: MemoryDatabase) -> None:
        self.db = db

    def upsert_memory(
        self,
        category: MemoryCategory,
        key: str,
        value: str,
        importance: int = 5,
        source: MemorySource = MemorySource.USER,
    ) -> MemoryRecord:
        """Create or update a structured memory by category and key."""
        clean_key = key.strip().lower()
        clean_val = value.strip()
        clamped_imp = max(1, min(10, importance))
        now = datetime.now(timezone.utc).isoformat()
        mem_id = str(uuid.uuid4())

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, category, key, value, importance, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value = excluded.value,
                    importance = excluded.importance,
                    source = excluded.source,
                    updated_at = excluded.updated_at;
                """,
                (
                    mem_id,
                    category.value,
                    clean_key,
                    clean_val,
                    clamped_imp,
                    source.value,
                    now,
                    now,
                ),
            )

            # Retrieve persisted record to guarantee returned ID matches
            row = conn.execute(
                "SELECT id, category, key, value, importance, source, created_at, updated_at FROM memories WHERE category = ? AND key = ?;",
                (category.value, clean_key),
            ).fetchone()

        logger.info(
            "Persisted memory [%s] %s=%s (importance=%d, source=%s)",
            category.value,
            clean_key,
            clean_val[:30],
            clamped_imp,
            source.value,
        )

        return MemoryRecord(
            id=row["id"],
            category=MemoryCategory(row["category"]),
            key=row["key"],
            value=row["value"],
            importance=row["importance"],
            source=MemorySource(row["source"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_memory(
        self,
        key: str,
        category: Optional[MemoryCategory] = None,
    ) -> Optional[MemoryRecord]:
        """Fetch exact memory by key and optional category."""
        clean_key = key.strip().lower()
        query = "SELECT id, category, key, value, importance, source, created_at, updated_at FROM memories WHERE key = ?"
        params: list[object] = [clean_key]
        if category:
            query += " AND category = ?"
            params.append(category.value)

        with self.db.transaction() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
            if not row:
                return None
            return MemoryRecord(
                id=row["id"],
                category=MemoryCategory(row["category"]),
                key=row["key"],
                value=row["value"],
                importance=row["importance"],
                source=MemorySource(row["source"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def search_memories(
        self,
        query: Optional[str] = None,
        category: Optional[MemoryCategory] = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Search memories using deterministic parameterized substring and category matching."""
        sql = "SELECT id, category, key, value, importance, source, created_at, updated_at FROM memories WHERE 1=1"
        params: list[object] = []

        if category:
            sql += " AND category = ?"
            params.append(category.value)

        if query and query.strip():
            clean_q = f"%{query.strip().lower()}%"
            sql += " AND (LOWER(key) LIKE ? OR LOWER(value) LIKE ?)"
            params.extend([clean_q, clean_q])

        sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        with self.db.transaction() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [
                MemoryRecord(
                    id=r["id"],
                    category=MemoryCategory(r["category"]),
                    key=r["key"],
                    value=r["value"],
                    importance=r["importance"],
                    source=MemorySource(r["source"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def delete_memory(
        self,
        key: str,
        category: Optional[MemoryCategory] = None,
    ) -> bool:
        """Delete matching memory by key and optional category."""
        clean_key = key.strip().lower()
        sql = "DELETE FROM memories WHERE key = ?"
        params: list[object] = [clean_key]
        if category:
            sql += " AND category = ?"
            params.append(category.value)

        with self.db.transaction() as conn:
            cur = conn.execute(sql, tuple(params))
            deleted = cur.rowcount > 0

        if deleted:
            logger.info("Deleted memory key='%s' category='%s'", clean_key, category)
        return deleted

    def list_memories(
        self,
        category: Optional[MemoryCategory] = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        """List stored memories ordered by importance and update timestamp."""
        return self.search_memories(category=category, limit=limit)
