from datetime import date
from decimal import Decimal
from database.db import get_connection, to_decimal


def _next_purchase_no(conn, p_date_str: str) -> str:
    year = p_date_str[:4]
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM purchases").fetchone()
    return f"PUR-{year}-{int(row['next_id']):04d}"


def create_supplier(
    name: str,
    phone: str = "",
    address: str = "",
    pincode: str = "",
    notes: str = "",
    db_path: str | None = None,
) -> dict:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Supplier name is required.")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO suppliers (name, phone, address, pincode, notes) VALUES (?, ?, ?, ?, ?)",
            (clean_name, phone.strip(), address.strip(), pincode.strip(), notes.strip()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_suppliers_with_balances(db_path: str | None = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                s.*,
                COALESCE(SUM(CAST(p.total_amount AS REAL)), 0) AS total_purchased,
                COALESCE(SUM(CAST(p.paid_amount AS REAL)), 0) AS total_paid,
                COALESCE(SUM(CAST(p.total_amount AS REAL) - CAST(p.paid_amount AS REAL)), 0) AS outstanding_balance
            FROM suppliers s
            LEFT JOIN purchases p ON p.supplier_id = s.id
            GROUP BY s.id
            ORDER BY outstanding_balance DESC, s.name ASC
            """
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["total_purchased"] = str(to_decimal(d["total_purchased"]))
            d["total_paid"] = str(to_decimal(d["total_paid"]))
            d["outstanding_balance"] = str(to_decimal(d["outstanding_balance"]))
            result.append(d)
        return result
    finally:
        conn.close()


def record_purchase(
    supplier_id: int,
    items: list[dict],
    supplier_invoice_no: str = "",
    purchase_date: str | None = None,
    paid_amount=0,
    payment_method: str = "Cash",
    notes: str = "",
    db_path: str | None = None,
) -> dict:
    """Record goods received from a supplier and increase product stock atomically (FR-17, FR-18, FR-21)."""
    if not supplier_id:
        raise ValueError("Supplier is required.")
    if not items:
        raise ValueError("Add at least one product to record a purchase.")

    p_date = (purchase_date or date.today().isoformat()).strip()
    paid = to_decimal(paid_amount)
    if paid < 0:
        raise ValueError("Paid amount cannot be negative.")

    conn = get_connection(db_path)
    try:
        sup = conn.execute("SELECT id FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if not sup:
            raise ValueError("Selected supplier does not exist.")

        prepared = []
        total_amount = Decimal("0.00")
        for entry in items:
            pid = int(entry["product_id"])
            qty = to_decimal(entry["quantity"])
            cost = to_decimal(entry["unit_cost"])
            if qty <= Decimal("0.00") or cost < Decimal("0.00"):
                raise ValueError("Purchase quantity must be positive and cost non-negative.")

            prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if not prod:
                raise ValueError(f"Product ID {pid} not found.")

            line_total = to_decimal(qty * cost)
            total_amount += line_total
            prepared.append({
                "product_id": pid,
                "prev_qty": to_decimal(prod["stock_qty"]),
                "qty": qty,
                "cost": cost,
                "line_total": line_total,
            })

        if paid > total_amount:
            raise ValueError("Paid amount cannot exceed total purchase amount.")

        purchase_no = _next_purchase_no(conn, p_date)
        cur = conn.execute(
            """
            INSERT INTO purchases (purchase_no, supplier_id, supplier_invoice_no, total_amount, paid_amount, purchase_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (purchase_no, supplier_id, supplier_invoice_no.strip(), total_amount, paid, p_date, notes.strip()),
        )
        purchase_id = cur.lastrowid

        for line in prepared:
            conn.execute(
                """
                INSERT INTO purchase_items (purchase_id, product_id, quantity, unit_cost, line_total)
                VALUES (?, ?, ?, ?, ?)
                """,
                (purchase_id, line["product_id"], line["qty"], line["cost"], line["line_total"]),
            )
            new_qty = line["prev_qty"] + line["qty"]
            conn.execute(
                "UPDATE products SET stock_qty = ?, purchase_cost = ? WHERE id = ?",
                (new_qty, line["cost"], line["product_id"]),
            )
            conn.execute(
                """
                INSERT INTO stock_movements (product_id, movement_type, quantity_change, previous_qty, new_qty, reference_code, note)
                VALUES (?, 'PURCHASE', ?, ?, ?, ?, ?)
                """,
                (line["product_id"], line["qty"], line["prev_qty"], new_qty, purchase_no, f"Purchase {purchase_no}"),
            )

        if paid > Decimal("0.00"):
            conn.execute(
                """
                INSERT INTO supplier_payments (supplier_id, purchase_id, amount, payment_method, payment_date, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (supplier_id, purchase_id, paid, payment_method, p_date, f"Initial payment on {purchase_no}"),
            )

        conn.commit()
        row = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_supplier_payment(
    purchase_id: int,
    amount,
    payment_method: str,
    payment_date: str | None = None,
    note: str = "",
    db_path: str | None = None,
) -> dict:
    """Record full or partial payment against a supplier purchase without altering stock (FR-18, FR-19)."""
    pay_amt = to_decimal(amount)
    if pay_amt <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")
    p_date = (payment_date or date.today().isoformat()).strip()

    conn = get_connection(db_path)
    try:
        pur = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        if not pur:
            raise ValueError("Purchase record not found.")
        balance = to_decimal(pur["total_amount"]) - to_decimal(pur["paid_amount"])
        if pay_amt > balance:
            raise ValueError(f"Payment (₹{pay_amt}) exceeds purchase balance (₹{balance}).")

        new_paid = to_decimal(pur["paid_amount"]) + pay_amt
        conn.execute("UPDATE purchases SET paid_amount = ? WHERE id = ?", (new_paid, purchase_id))
        conn.execute(
            """
            INSERT INTO supplier_payments (supplier_id, purchase_id, amount, payment_method, payment_date, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pur["supplier_id"], purchase_id, pay_amt, payment_method, p_date, note.strip() or f"Payment for {pur['purchase_no']}"),
        )
        conn.commit()
        return {"purchase_no": pur["purchase_no"], "new_balance": str(to_decimal(pur["total_amount"]) - new_paid)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_purchases(db_path: str | None = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT p.*, s.name AS supplier_name
            FROM purchases p
            JOIN suppliers s ON s.id = p.supplier_id
            ORDER BY p.id DESC
            """
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["balance"] = str(to_decimal(d["total_amount"]) - to_decimal(d["paid_amount"]))
            result.append(d)
        return result
    finally:
        conn.close()