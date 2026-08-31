"""Tests for MemoryDatabase lifecycle, schema versioning, transactions, and integrity."""

from pathlib import Path
import sqlite3
import pytest

from app.memory.database import MemoryDatabase


@pytest.fixture
def temp_db(tmp_path: Path) -> MemoryDatabase:
    db_file = tmp_path / "test_assistant.db"
    db = MemoryDatabase(db_path=db_file)
    db.initialize()
    return db


def test_database_creation_and_schema_version(temp_db: MemoryDatabase) -> None:
    assert temp_db.db_path.exists()
    assert temp_db.check_integrity() is True

    with temp_db.transaction() as conn:
        row = conn.execute("SELECT version, applied_at FROM schema_version;").fetchone()
        assert row is not None
        assert row["version"] == 1
        assert row["applied_at"] is not None


def test_schema_initialization_idempotency(temp_db: MemoryDatabase) -> None:
    # Initialize second and third time
    temp_db.initialize()
    temp_db.initialize()

    with temp_db.transaction() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM schema_version;").fetchone()["cnt"]
        assert count == 1


def test_foreign_key_cascade_deletion(temp_db: MemoryDatabase) -> None:
    conv_id = "test-conv-1"
    with temp_db.transaction() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, '2026-08-30T00:00:00Z', '2026-08-30T00:00:00Z');",
            (conv_id, "Test Conv"),
        )
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, sequence_number, created_at) VALUES (?, ?, 'user', 'hello', 1, '2026-08-30T00:00:00Z');",
            ("msg-1", conv_id),
        )

    # Verify message exists
    with temp_db.transaction() as conn:
        m_count = conn.execute("SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?;", (conv_id,)).fetchone()["cnt"]
        assert m_count == 1

    # Delete parent conversation
    with temp_db.transaction() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ?;", (conv_id,))

    # Messages must be deleted due to ON DELETE CASCADE
    with temp_db.transaction() as conn:
        m_count = conn.execute("SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?;", (conv_id,)).fetchone()["cnt"]
        assert m_count == 0


def test_transaction_rollback_on_error(temp_db: MemoryDatabase) -> None:
    with pytest.raises(RuntimeError):
        with temp_db.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, '2026-08-30T00:00:00Z', '2026-08-30T00:00:00Z');",
                ("rollback-conv", "Rollback Test"),
            )
            raise RuntimeError("Forced transaction failure")

    # Verify insertion was rolled back
    with temp_db.transaction() as conn:
        row = conn.execute("SELECT id FROM conversations WHERE id = 'rollback-conv';").fetchone()
        assert row is None


def test_integrity_check_failure_on_corrupt_file(tmp_path: Path) -> None:
    corrupt_file = tmp_path / "corrupt.db"
    corrupt_file.write_bytes(b"This is completely invalid sqlite data")

    bad_db = MemoryDatabase(db_path=corrupt_file)
    assert bad_db.check_integrity() is False
