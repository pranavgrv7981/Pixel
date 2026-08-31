"""Database backup, integrity verification, and safe local recovery."""

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("core.backup")


class DatabaseBackupManager:
    """Manages snapshot backups, SQLite PRAGMA integrity verification, and database recovery."""

    def __init__(self, backup_dir: Optional[Path] = None, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.backup_dir = (
            backup_dir or (self.settings.get_resolved_data_dir() / "backups")
        ).resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def verify_integrity(self, db_path: Path) -> bool:
        """Run SQLite PRAGMA integrity_check to confirm database is not corrupt."""
        if not db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            return bool(result and result[0] == "ok")
        except Exception as err:
            logger.warning("Integrity check failed on '%s': %s", db_path.name, err)
            return False

    def create_backup(self, db_path: Path, label: Optional[str] = None, max_keep: int = 5) -> Optional[Path]:
        """Create a consistent SQLite snapshot backup and rotate older snapshots."""
        if not db_path.exists():
            logger.warning("Cannot backup non-existent database: %s", db_path)
            return None

        # Verify integrity before backup
        if not self.verify_integrity(db_path):
            logger.error("Refusing to backup corrupted database: %s", db_path)
            return None

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tag = f"_{label}" if label else ""
        backup_filename = f"{db_path.stem}_{timestamp_str}{tag}.db"
        target_backup_path = self.backup_dir / backup_filename

        try:
            # Use SQLite backup API for consistent snapshot during active read/write
            src_conn = sqlite3.connect(str(db_path), timeout=10.0)
            dst_conn = sqlite3.connect(str(target_backup_path))
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            logger.info("Successfully created database backup: %s", target_backup_path.name)
            self.rotate_backups(db_path.stem, max_keep=max_keep)
            return target_backup_path
        except Exception as err:
            logger.error("Failed to create database backup for '%s': %s", db_path, err)
            if target_backup_path.exists():
                try:
                    target_backup_path.unlink()
                except OSError:
                    pass
            return None

    def list_backups(self, db_stem: Optional[str] = None) -> list[dict[str, Any]]:
        """List available backups sorted from newest to oldest."""
        backups: list[dict[str, Any]] = []
        if not self.backup_dir.exists():
            return backups

        for f in sorted(self.backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
            if db_stem and not f.name.startswith(db_stem):
                continue
            try:
                stat = f.stat()
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                })
            except OSError:
                continue
        return backups

    def restore_backup(self, backup_path: Path, target_db_path: Path) -> bool:
        """Safely restore a database from a verified backup snapshot."""
        if not backup_path.exists():
            logger.error("Restore failed: Backup file does not exist: %s", backup_path)
            return False

        if not self.verify_integrity(backup_path):
            logger.error("Restore failed: Backup file '%s' is corrupted.", backup_path)
            return False

        # Create temporary pre-restore snapshot of current database if it exists
        pre_restore_bak = None
        if target_db_path.exists():
            pre_restore_bak = target_db_path.with_suffix(".pre_restore.bak")
            try:
                shutil.copy2(target_db_path, pre_restore_bak)
            except Exception as err:
                logger.warning("Could not create pre-restore snapshot: %s", err)

        try:
            target_db_path.parent.mkdir(parents=True, exist_ok=True)
            # Use SQLite backup API to write into target
            src_conn = sqlite3.connect(str(backup_path))
            dst_conn = sqlite3.connect(str(target_db_path), timeout=10.0)
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            # Clean up pre-restore backup upon success
            if pre_restore_bak and pre_restore_bak.exists():
                try:
                    pre_restore_bak.unlink()
                except OSError:
                    pass

            logger.info("Database '%s' successfully restored from '%s'", target_db_path.name, backup_path.name)
            return True
        except Exception as err:
            logger.error("Failed to restore database from '%s': %s", backup_path, err)
            # Rollback to pre-restore snapshot if restore failed
            if pre_restore_bak and pre_restore_bak.exists():
                try:
                    shutil.move(str(pre_restore_bak), str(target_db_path))
                except Exception:
                    pass
            return False

    def rotate_backups(self, db_stem: str, max_keep: int = 5) -> int:
        """Prune older backups for a database stem to conserve disk space."""
        backups = [f for f in sorted(self.backup_dir.glob(f"{db_stem}_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)]
        pruned = 0
        if len(backups) > max_keep:
            for old_bak in backups[max_keep:]:
                try:
                    old_bak.unlink()
                    pruned += 1
                except OSError as err:
                    logger.warning("Could not prune old backup '%s': %s", old_bak.name, err)
        return pruned
