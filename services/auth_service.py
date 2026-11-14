from werkzeug.security import check_password_hash, generate_password_hash
from database.db import get_connection, to_decimal


def authenticate_user(username: str, password: str, db_path: str | None = None) -> dict | None:
    """Verify username and password hash. Returns user dict or None."""
    if not username or not password:
        return None
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            return {"id": row["id"], "username": row["username"]}
        return None
    finally:
        conn.close()


def change_password(user_id: int, current_password: str, new_password: str, db_path: str | None = None) -> tuple[bool, str]:
    """Update operator password after checking current password."""
    if not new_password or len(new_password) < 6:
        return False, "New password must be at least 6 characters."
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], current_password):
            return False, "Current password is incorrect."
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )
        conn.commit()
        return True, "Password updated successfully."
    finally:
        conn.close()


def get_store_settings(db_path: str | None = None) -> dict:
    """Fetch store configuration (name, address, phone, default tax rate)."""
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM store_settings WHERE id = 1").fetchone()
        return dict(row) if row else {
            "store_name": "ElectroDesk Electricals",
            "store_address": "Main Market Road, Goa",
            "store_phone": "",
            "default_tax_rate": "0.00",
        }
    finally:
        conn.close()


def update_store_settings(
    store_name: str,
    store_address: str,
    store_phone: str,
    default_tax_rate,
    db_path: str | None = None,
) -> None:
    """Save updated store settings."""
    tax = to_decimal(default_tax_rate)
    if tax < 0 or tax > 100:
        raise ValueError("Tax rate must be between 0 and 100.")
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE store_settings
            SET store_name = ?, store_address = ?, store_phone = ?, default_tax_rate = ?
            WHERE id = 1
            """,
            (store_name.strip() or "ElectroDesk Electricals", store_address.strip(), store_phone.strip(), tax),
        )
        conn.commit()
    finally:
        conn.close()