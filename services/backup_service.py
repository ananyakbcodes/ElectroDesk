import os
import sqlite3
from datetime import datetime, date
from config import Config


def create_backup(
    db_path: str | None = None,
    backup_dir: str | None = None,
    prefix: str = "manual",
) -> str:
    """Create a consistent SQLite backup copy in a separate folder (FR-40, FR-41)."""
    src_path = db_path or Config.DB_PATH
    target_dir = backup_dir or Config.BACKUP_DIR
    os.makedirs(target_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_filename = f"electrodesk_{prefix}_{timestamp}.db"
    dest_path = os.path.join(target_dir, backup_filename)

    src_conn = sqlite3.connect(src_path)
    dest_conn = sqlite3.connect(dest_path)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    return dest_path


def run_daily_auto_backup(
    db_path: str | None = None,
    backup_dir: str | None = None,
    keep_last: int = 30,
) -> str | None:
    """Create one automatic backup per calendar day and prune older auto-backups (FR-39)."""
    src_path = db_path or Config.DB_PATH
    if not os.path.exists(src_path):
        return None

    target_dir = backup_dir or Config.BACKUP_DIR
    os.makedirs(target_dir, exist_ok=True)
    today_tag = f"electrodesk_daily_{date.today().strftime('%Y%m%d')}_"

    existing_today = [f for f in os.listdir(target_dir) if f.startswith(today_tag) and f.endswith(".db")]
    if existing_today:
        return None

    created = create_backup(db_path=src_path, backup_dir=target_dir, prefix="daily")

    # Retain only the most recent `keep_last` daily backups
    daily_files = sorted(
        [os.path.join(target_dir, f) for f in os.listdir(target_dir) if f.startswith("electrodesk_daily_") and f.endswith(".db")]
    )
    while len(daily_files) > keep_last:
        old_file = daily_files.pop(0)
        os.remove(old_file)

    return created


def list_backups(backup_dir: str | None = None) -> list[dict]:
    target_dir = backup_dir or Config.BACKUP_DIR
    if not os.path.exists(target_dir):
        return []
    files = []
    for fname in sorted(os.listdir(target_dir), reverse=True):
        if fname.endswith(".db"):
            full = os.path.join(target_dir, fname)
            stat = os.stat(full)
            files.append({
                "filename": fname,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
    return files


def restore_backup_to_target(backup_path: str, target_db_path: str) -> bool:
    """Verify integrity of a backup file and restore it to a target path (FR-42)."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError("Backup file does not exist.")

    check_conn = sqlite3.connect(backup_path)
    try:
        integrity = check_conn.execute("PRAGMA integrity_check;").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Backup integrity check failed: {integrity}")
    finally:
        check_conn.close()

    os.makedirs(os.path.dirname(os.path.abspath(target_db_path)), exist_ok=True)
    src = sqlite3.connect(backup_path)
    dst = sqlite3.connect(target_db_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return True