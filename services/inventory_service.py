import csv
import io
from decimal import Decimal
from database.db import get_connection, to_decimal

ALLOWED_UNITS = ("pcs", "box", "metre", "roll", "kg")


def _next_product_code(conn) -> str:
    """Generate sequential internal code like ELC-0001."""
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM products").fetchone()
    return f"ELC-{int(row['next_id']):04d}"


def add_product(
    name: str,
    unit: str,
    selling_price,
    purchase_cost=0,
    initial_stock=0,
    min_stock_threshold=5,
    db_path: str | None = None,
) -> dict:
    """Create a new product and log Day-1 Opening Stock if initial_stock > 0."""
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Product name is required.")
    clean_unit = (unit or "pcs").strip().lower()
    if clean_unit not in ALLOWED_UNITS:
        raise ValueError(f"Unit must be one of: {', '.join(ALLOWED_UNITS)}.")

    price = to_decimal(selling_price)
    cost = to_decimal(purchase_cost)
    qty = to_decimal(initial_stock)
    min_qty = to_decimal(min_stock_threshold)

    if price < 0 or cost < 0 or qty < 0 or min_qty < 0:
        raise ValueError("Prices, stock, and thresholds cannot be negative.")

    conn = get_connection(db_path)
    try:
        code = _next_product_code(conn)
        cur = conn.execute(
            """
            INSERT INTO products (product_code, name, unit, selling_price, purchase_cost, stock_qty, min_stock_threshold)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (code, clean_name, clean_unit, price, cost, qty, min_qty),
        )
        product_id = cur.lastrowid

        if qty > Decimal("0.00"):
            conn.execute(
                """
                INSERT INTO stock_movements (product_id, movement_type, quantity_change, previous_qty, new_qty, reference_code, note)
                VALUES (?, 'OPENING', ?, 0.00, ?, ?, 'Day-1 Opening Stock')
                """,
                (product_id, qty, qty, code),
            )

        conn.commit()
        return get_product_by_id(product_id, db_path)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_product(
    product_id: int,
    name: str,
    unit: str,
    selling_price,
    purchase_cost,
    min_stock_threshold,
    is_active: bool = True,
    db_path: str | None = None,
) -> dict:
    """Edit product metadata without altering past bills or direct stock."""
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Product name is required.")
    clean_unit = (unit or "pcs").strip().lower()
    if clean_unit not in ALLOWED_UNITS:
        raise ValueError(f"Unit must be one of: {', '.join(ALLOWED_UNITS)}.")

    price = to_decimal(selling_price)
    cost = to_decimal(purchase_cost)
    min_qty = to_decimal(min_stock_threshold)
    if price < 0 or cost < 0 or min_qty < 0:
        raise ValueError("Prices and thresholds cannot be negative.")

    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE products
            SET name = ?, unit = ?, selling_price = ?, purchase_cost = ?, min_stock_threshold = ?, is_active = ?
            WHERE id = ?
            """,
            (clean_name, clean_unit, price, cost, min_qty, 1 if is_active else 0, product_id),
        )
        conn.commit()
        return get_product_by_id(product_id, db_path)
    finally:
        conn.close()


def get_product_by_id(product_id: int, db_path: str | None = None) -> dict | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_products(search: str = "", active_only: bool = False, db_path: str | None = None) -> list[dict]:
    """List products with optional name/code search and active filter."""
    conn = get_connection(db_path)
    try:
        sql = "SELECT * FROM products WHERE 1=1"
        params = []
        if active_only:
            sql += " AND is_active = 1"
        if search and search.strip():
            term = f"%{search.strip()}%"
            sql += " AND (name LIKE ? OR product_code LIKE ?)"
            params.extend([term, term])
        sql += " ORDER BY is_active DESC, name ASC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_low_stock_products(db_path: str | None = None) -> list[dict]:
    """Return active products whose current stock <= min_stock_threshold (FR-05)."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM products
            WHERE is_active = 1 AND CAST(stock_qty AS REAL) <= CAST(min_stock_threshold AS REAL)
            ORDER BY CAST(stock_qty AS REAL) ASC, name ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def reconcile_stock(product_id: int, counted_qty, note: str = "", db_path: str | None = None) -> dict:
    """Adjust stock to physical shelf count and log variance in stock_movements (FR-06)."""
    counted = to_decimal(counted_qty)
    if counted < 0:
        raise ValueError("Counted quantity cannot be negative.")

    conn = get_connection(db_path)
    try:
        prod = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not prod:
            raise ValueError("Product not found.")

        prev_qty = to_decimal(prod["stock_qty"])
        diff = counted - prev_qty

        conn.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (counted, product_id))
        conn.execute(
            """
            INSERT INTO stock_movements (product_id, movement_type, quantity_change, previous_qty, new_qty, reference_code, note)
            VALUES (?, 'RECONCILIATION', ?, ?, ?, ?, ?)
            """,
            (product_id, diff, prev_qty, counted, prod["product_code"], note.strip() or "Physical stock check"),
        )
        conn.commit()
        return {
            "product_code": prod["product_code"],
            "name": prod["name"],
            "previous_qty": str(prev_qty),
            "counted_qty": str(counted),
            "difference": str(diff),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_recent_stock_movements(limit: int = 30, db_path: str | None = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT sm.*, p.name AS product_name, p.product_code, p.unit
            FROM stock_movements sm
            JOIN products p ON p.id = sm.product_id
            ORDER BY sm.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def import_products_csv(csv_text: str, db_path: str | None = None) -> dict:
    """
    Validate and import products from CSV text (FR-07, FR-46).
    Expected headers: name, unit, selling_price, purchase_cost, stock_qty, min_stock_threshold
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    required_cols = {"name", "unit", "selling_price"}
    if not reader.fieldnames or not required_cols.issubset({c.strip().lower() for c in reader.fieldnames}):
        return {
            "imported": 0,
            "errors": ["CSV must include headers: name, unit, selling_price (optional: purchase_cost, stock_qty, min_stock_threshold)."],
        }

    imported_count = 0
    errors = []
    for row_num, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
        try:
            add_product(
                name=row.get("name", ""),
                unit=row.get("unit", "pcs"),
                selling_price=row.get("selling_price", ""),
                purchase_cost=row.get("purchase_cost") or "0",
                initial_stock=row.get("stock_qty") or "0",
                min_stock_threshold=row.get("min_stock_threshold") or "5",
                db_path=db_path,
            )
            imported_count += 1
        except Exception as exc:
            errors.append(f"Row {row_num} ({row.get('name', 'unnamed')}): {exc}")

    return {"imported": imported_count, "errors": errors}