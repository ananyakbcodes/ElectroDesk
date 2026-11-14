import os
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from werkzeug.security import generate_password_hash
from config import Config

# Teach SQLite how to store Python Decimal values cleanly
sqlite3.register_adapter(Decimal, lambda d: str(d))


def to_decimal(value) -> Decimal:
    """Convert any numeric or string input to an exact 2-decimal-place Decimal."""
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with Foreign Keys and WAL mode enabled."""
    target_path = db_path or Config.DB_PATH
    conn = sqlite3.connect(target_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create all tables from schema.sql and seed default settings & operator account."""
    target_path = db_path or Config.DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    os.makedirs(Config.BACKUP_DIR, exist_ok=True)

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_connection(target_path)
    try:
        conn.executescript(schema_sql)

        # Ensure default store configuration row exists (FR-38A)
        conn.execute(
            """
            INSERT OR IGNORE INTO store_settings (id, store_name, store_address, store_phone, default_tax_rate)
            VALUES (1, 'ElectroDesk Electricals', 'Main Market Road, Goa', '', 0.00)
            """
        )

        # Ensure default operator account exists with hashed password (FR-35, FR-37)
        existing_user = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (Config.DEFAULT_ADMIN_USER,),
        ).fetchone()

        if not existing_user:
            hashed = generate_password_hash(Config.DEFAULT_ADMIN_PASS)
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (Config.DEFAULT_ADMIN_USER, hashed),
            )

        conn.commit()
    finally:
        conn.close()