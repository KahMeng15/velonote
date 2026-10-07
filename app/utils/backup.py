"""Database backup utility using pg_dump with retention management."""

import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.models.db import SystemSettings
from app.utils.db import SessionLocal

logger = logging.getLogger(__name__)


def resolve_backup_dir() -> Path:
    """Resolve the directory where database backups are stored."""
    # Check explicit environment variable
    custom_dir = os.getenv("BACKUP_DIR")
    if custom_dir:
        path = Path(custom_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # If running in container with /app/backups mounted
    container_backups = Path("/app/backups")
    if container_backups.exists() or Path("/app").exists():
        try:
            container_backups.mkdir(parents=True, exist_ok=True)
            return container_backups
        except Exception:
            pass

    # Default to local workspace path
    local_backups = Path("backups/postgres")
    local_backups.mkdir(parents=True, exist_ok=True)
    return local_backups


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable units."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def validate_backup_filename(filename: str) -> None:
    """Validate filename to prevent path traversal and restrict to backup files."""
    if not filename:
        raise ValueError("Filename is required")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("Invalid filename: directory traversal detected")
    if not (filename.startswith("backup_") and (filename.endswith(".sql") or filename.endswith(".sql.gz"))):
        raise ValueError("Invalid backup filename format")


def perform_db_backup(backup_dir: Path | str | None = None, force: bool = False) -> bool:
    """
    Perform a PostgreSQL database backup via pg_dump and prune expired backups.
    Reads backup_enabled and backup_retention_days from SystemSettings unless force is True.
    """
    settings = get_settings()

    # Query retention and enabled status from SystemSettings
    backup_enabled = True
    retention_days = 7
    try:
        db = SessionLocal()
        try:
            sys_settings = db.query(SystemSettings).first()
            if sys_settings:
                if sys_settings.backup_enabled is not None:
                    backup_enabled = sys_settings.backup_enabled
                if sys_settings.backup_retention_days is not None:
                    retention_days = sys_settings.backup_retention_days
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not load backup settings from DB, using defaults: {e}")

    if not force and not backup_enabled:
        logger.info("Database backup is disabled in system settings. Skipping backup.")
        return True

    target_dir = Path(backup_dir) if backup_dir else resolve_backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check pg_dump availability
    pg_dump_bin = shutil.which("pg_dump")
    if not pg_dump_bin:
        logger.warning(
            "pg_dump binary not found in system PATH. Install postgresql-client to enable database backups."
        )
        return False

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = target_dir / f"backup_{ts}.sql"

    env = os.environ.copy()
    if settings.DB_PASSWORD:
        env["PGPASSWORD"] = settings.DB_PASSWORD

    cmd = [
        pg_dump_bin,
        "-h", settings.DB_HOST,
        "-p", str(settings.DB_PORT),
        "-U", settings.DB_USER,
        "-d", settings.DB_NAME,
        "-f", str(backup_file),
    ]

    logger.info(f"Starting database backup to {backup_file}...")
    try:
        subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
        size_bytes = backup_file.stat().st_size
        logger.info(
            f"Database backup created successfully: {backup_file.name} ({format_size(size_bytes)})"
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"pg_dump failed with exit code {e.returncode}: {e.stderr.strip()}")
        if backup_file.exists():
            backup_file.unlink()
        return False
    except Exception as e:
        logger.error(f"Database backup failed unexpectedly: {e}")
        if backup_file.exists():
            backup_file.unlink()
        return False

    # Prune old backups
    prune_old_backups(target_dir, retention_days)
    return True


def create_manual_backup(backup_dir: Path | str | None = None) -> dict:
    """
    Manually create a backup immediately (bypassing backup_enabled setting)
    and return metadata about the created backup.
    Raises RuntimeError on failure.
    """
    settings = get_settings()
    target_dir = Path(backup_dir) if backup_dir else resolve_backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    pg_dump_bin = shutil.which("pg_dump")
    if not pg_dump_bin:
        raise RuntimeError("pg_dump binary not found in system PATH. Install postgresql-client on the server.")

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = target_dir / f"backup_{ts}.sql"

    env = os.environ.copy()
    if settings.DB_PASSWORD:
        env["PGPASSWORD"] = settings.DB_PASSWORD

    cmd = [
        pg_dump_bin,
        "-h", settings.DB_HOST,
        "-p", str(settings.DB_PORT),
        "-U", settings.DB_USER,
        "-d", settings.DB_NAME,
        "-f", str(backup_file),
    ]

    try:
        subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
        stat = backup_file.stat()
        return {
            "filename": backup_file.name,
            "size_bytes": stat.st_size,
            "size_formatted": format_size(stat.st_size),
            "created_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
        }
    except subprocess.CalledProcessError as e:
        if backup_file.exists():
            backup_file.unlink()
        raise RuntimeError(f"pg_dump failed (exit code {e.returncode}): {e.stderr.strip()}")
    except Exception as e:
        if backup_file.exists():
            backup_file.unlink()
        raise RuntimeError(f"Database backup failed: {e}")


def list_backups(backup_dir: Path | str | None = None) -> list[dict]:
    """List all available database backup files ordered by newest first."""
    target_dir = Path(backup_dir) if backup_dir else resolve_backup_dir()
    if not target_dir.exists():
        return []

    backups = []
    for file_path in target_dir.glob("backup_*.sql*"):
        if file_path.is_file():
            stat = file_path.stat()
            backups.append({
                "filename": file_path.name,
                "size_bytes": stat.st_size,
                "size_formatted": format_size(stat.st_size),
                "created_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
            })

    backups.sort(key=lambda b: b["created_at"], reverse=True)
    return backups


def get_backup_file_path(filename: str, backup_dir: Path | str | None = None) -> Path:
    """Get validated path to a backup file."""
    validate_backup_filename(filename)
    target_dir = Path(backup_dir) if backup_dir else resolve_backup_dir()
    file_path = (target_dir / filename).resolve()

    if not str(file_path).startswith(str(target_dir.resolve())):
        raise ValueError("Access denied: path traversal attempt")

    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"Backup file '{filename}' not found")

    return file_path


def delete_backup_file(filename: str, backup_dir: Path | str | None = None) -> bool:
    """Delete a specific backup file."""
    file_path = get_backup_file_path(filename, backup_dir)
    file_path.unlink()
    logger.info(f"Deleted database backup: {filename}")
    return True


def prune_old_backups(backup_dir: Path, retention_days: int):
    """Delete backups older than retention_days."""
    if retention_days <= 0:
        return

    now = datetime.utcnow().timestamp()
    cutoff_seconds = retention_days * 86400
    count_deleted = 0

    for file_path in backup_dir.glob("backup_*.sql*"):
        try:
            file_age = now - file_path.stat().st_mtime
            if file_age > cutoff_seconds:
                file_path.unlink()
                count_deleted += 1
                logger.info(f"Pruned expired backup: {file_path.name}")
        except Exception as e:
            logger.warning(f"Error checking/pruning backup file {file_path}: {e}")

    if count_deleted > 0:
        logger.info(f"Cleaned up {count_deleted} expired database backup(s)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    success = perform_db_backup()
    if not success:
        exit(1)
