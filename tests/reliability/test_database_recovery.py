"""Reliability tests for SQLite integrity checks, backups, and recovery."""

import pytest
import sqlite3
from pathlib import Path
from app.core.backup import DatabaseBackupManager


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "sample.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('Alice'), ('Bob')")
    conn.commit()
    conn.close()
    return db_file


def test_database_integrity_verification(sample_db: Path, tmp_path: Path) -> None:
    mgr = DatabaseBackupManager(backup_dir=tmp_path / "backups")
    assert mgr.verify_integrity(sample_db) is True

    # Corrupt a non-sqlite file
    corrupt_file = tmp_path / "corrupt.db"
    corrupt_file.write_text("NOT A SQLITE FILE HEADER", encoding="utf-8")
    assert mgr.verify_integrity(corrupt_file) is False


def test_database_backup_and_restore_cycle(sample_db: Path, tmp_path: Path) -> None:
    mgr = DatabaseBackupManager(backup_dir=tmp_path / "backups")

    # 1. Create backup
    backup_file = mgr.create_backup(sample_db, label="test_snap")
    assert backup_file is not None
    assert backup_file.exists()
    assert mgr.verify_integrity(backup_file) is True

    # 2. Modify original database
    conn = sqlite3.connect(str(sample_db))
    conn.execute("INSERT INTO users (name) VALUES ('Charlie')")
    conn.commit()
    conn.close()

    # 3. Restore from backup
    success = mgr.restore_backup(backup_file, sample_db)
    assert success is True

    # 4. Verify restored state
    conn = sqlite3.connect(str(sample_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 2  # Restored to original Alice and Bob
